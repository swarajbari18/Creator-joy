"""
End-to-end transcription test.

Usage:
    cd backend
    export $(grep -v '^#' .env | xargs)
    python -m tests.dev_test_transcription

To transcribe a specific video by ID, set VIDEO_ID below.
To ingest a fresh video first, set INGEST_URL instead.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from creator_joy.ingestion import VideoIngestionService
from creator_joy.ingestion.logging_config import configure_debug_logging
from creator_joy.transcription import TranscriptionService, TranscriptionSettings

# ── Configuration ────────────────────────────────────────────────────────────

# Option A: transcribe a video already in the database (fill in a real video ID)
VIDEO_ID: str | None = "c8604c66-2a5d-4ce4-96b8-43186fad1e46"

# Option B: ingest + transcribe a fresh URL (set VIDEO_ID = None and provide a URL here)
INGEST_URL: str | None = None  # e.g. "https://www.youtube.com/watch?v=..."

# Storage root — must match where ingestion stored its data
STORAGE_ROOT = Path(__file__).parent.parent / "downloads"

# ── Helpers ──────────────────────────────────────────────────────────────────


def _print_section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def main() -> None:
    configure_debug_logging()

    settings = TranscriptionSettings(storage_root=STORAGE_ROOT)

    video_id = VIDEO_ID

    # Ingest a fresh video if requested
    if video_id is None:
        if not INGEST_URL:
            print("ERROR: Set VIDEO_ID or INGEST_URL at the top of this script.", file=sys.stderr)
            sys.exit(1)

        _print_section("Ingesting video")
        ingestion_service = VideoIngestionService()
        project = ingestion_service.create_project("transcription-test")
        print(f"Project: {project.id}")
        videos = ingestion_service.ingest_urls(project.id, [INGEST_URL])
        video = videos[0]
        if video.status != "completed":
            print(f"ERROR: Ingestion failed — {video.error_message}", file=sys.stderr)
            sys.exit(1)
        video_id = video.id
        print(f"Ingested video_id: {video_id}")

    # Run transcription
    _print_section(f"Transcribing video_id={video_id}")
    service = TranscriptionService(settings=settings)
    record = service.transcribe_video(video_id)

    _print_section("Result")
    print(f"Status:            {record.status}")
    print(f"Gemini model:      {record.gemini_model}")
    print(f"Transcription path: {record.transcription_path}")

    if record.transcription_path and Path(record.transcription_path).exists():
        data = json.loads(Path(record.transcription_path).read_text(encoding="utf-8"))

        _print_section("Document-level fields")
        for key in ("video_id", "platform", "title", "creator_name", "total_duration", "resolution"):
            print(f"  {key}: {data.get(key)}")

        speakers = data.get("speakers", {})
        print(f"\nSpeakers identified: {len(speakers)}")
        for sid, info in speakers.items():
            print(f"  {sid}: {info.get('identified_name')} ({info.get('role')})")

        segments = data.get("segments", [])
        print(f"\nTotal segments: {len(segments)}")

        _print_section("First 3 segments")
        for seg in segments[:3]:
            print(f"\n  Segment {seg['segment_id']} [{seg['timecode_start']} → {seg['timecode_end']}]")
            print(f"  Summary:  {seg.get('observable_summary', '')}")
            print(f"  Speech:   {seg['speech']['transcript'][:120]!r}")
            print(f"  Shot:     {seg['frame']['shot_type']} / {seg['frame']['camera_angle']}")
            text_entries = seg.get("on_screen_text", {}).get("entries", [])
            if text_entries:
                print(f"  Overlays: {[e['text'] for e in text_entries]}")
    else:
        print("ERROR: transcription.json not found on disk.", file=sys.stderr)
        if record.error_message:
            print(f"Error: {record.error_message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
