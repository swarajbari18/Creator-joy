from __future__ import annotations

import json
import logging
from pathlib import Path

from creator_joy.ingestion.database import IngestionDatabase
from creator_joy.ingestion.models import VideoFileKind
from creator_joy.transcription.database import TranscriptionDatabase
from creator_joy.transcription.models import TranscriptionRecord, TranscriptionSettings, TranscriptionStatus
from creator_joy.transcription.schema import RichVideoTranscription
from creator_joy.transcription.transcriber import GeminiTranscriber

logger = logging.getLogger(__name__)


def _seconds_to_mmss(seconds: float | None) -> str:
    if seconds is None:
        return "[unknown]"
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


class TranscriptionService:
    def __init__(self, settings: TranscriptionSettings | None = None) -> None:
        self.settings = settings or TranscriptionSettings()
        logger.debug("Creating TranscriptionService settings=%s", self.settings)
        self.settings.storage_root.mkdir(parents=True, exist_ok=True)
        self.ingestion_db = IngestionDatabase(self.settings.database_path)
        self.transcription_db = TranscriptionDatabase(self.settings.database_path)
        self.transcriber = GeminiTranscriber(self.settings)

    def transcribe_video(self, video_id: str) -> TranscriptionRecord:
        logger.debug("Service transcribe_video video_id=%s", video_id)

        video = self.ingestion_db.get_video(video_id)
        if video is None:
            raise ValueError(f"Video does not exist: {video_id}")

        video_files = self.ingestion_db.list_video_files(video_id)

        # Prefer .mp4 explicitly — yt-dlp also registers thumbnail .webp files under kind=video
        _VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi"}
        video_file = next(
            (
                f for f in video_files
                if f.kind == VideoFileKind.VIDEO
                and Path(f.path).suffix.lower() in _VIDEO_EXTENSIONS
            ),
            None,
        )
        if video_file is None:
            raise RuntimeError(
                f"No playable video file (.mp4/.mkv/.webm) found for video_id={video_id}. "
                "Run ingestion first or check that the video downloaded successfully."
            )
        video_path = Path(video_file.path)

        metadata_file = next(
            (f for f in video_files if f.kind == VideoFileKind.METADATA),
            None,
        )
        metadata: dict = {}
        if metadata_file and Path(metadata_file.path).exists():
            metadata = json.loads(Path(metadata_file.path).read_text(encoding="utf-8"))

        record = self.transcription_db.create_or_reset_transcription(
            video_id=video_id,
            gemini_model=self.settings.gemini_model,
        )
        self.transcription_db.update_transcription_status(record.id, TranscriptionStatus.PROCESSING)
        logger.debug("Transcription record created id=%s status=processing", record.id)

        try:
            payload = self.transcriber.transcribe(video_path, video)

            transcription = RichVideoTranscription(
                video_id=video.id,
                source_url=video.source_url,
                platform=video.platform or metadata.get("extractor_key") or "unknown",
                title=video.title or metadata.get("title") or "[unknown]",
                creator_name=video.uploader or metadata.get("uploader") or metadata.get("channel") or "[unknown]",
                upload_date=video.upload_date or metadata.get("upload_date") or "[unknown]",
                total_duration=_seconds_to_mmss(video.duration),
                resolution=str(metadata.get("resolution") or metadata.get("height") or "[unknown]"),
                aspect_ratio=str(metadata.get("aspect_ratio") or "[unknown]"),
                speakers=payload.speakers,
                segments=payload.segments,
            )

            output_dir = video_path.parent
            transcription_path = output_dir / "transcription.json"
            logger.debug("Writing transcription JSON video_id=%s path=%s", video_id, transcription_path)
            transcription_path.write_text(
                transcription.model_dump_json(indent=2),
                encoding="utf-8",
            )

            self.transcription_db.update_transcription_status(
                record.id,
                TranscriptionStatus.COMPLETED,
                transcription_path=str(transcription_path),
            )
            logger.debug("Transcription completed video_id=%s segments=%s", video_id, len(payload.segments))

        except Exception as exc:
            logger.exception("Transcription failed video_id=%s", video_id)
            self.transcription_db.update_transcription_status(
                record.id,
                TranscriptionStatus.FAILED,
                error_message=str(exc),
            )
            raise

        completed = self.transcription_db.get_transcription(record.id)
        if completed is None:
            raise RuntimeError(f"Completed transcription row disappeared: {record.id}")
        return completed

    def get_transcription(self, video_id: str) -> TranscriptionRecord | None:
        return self.transcription_db.get_transcription_for_video(video_id)
