"""
End-to-end RAG test.

Usage:
    cd backend
    export $(grep -v '^#' .env | xargs)
    python -m tests.dev_test_rag
"""
from __future__ import annotations
import sys
from pathlib import Path
from creator_joy.ingestion.logging_config import configure_debug_logging

from creator_joy.rag.service import RAGService
from creator_joy.rag.models import StructuralFilters

# ── Configuration ────────────────────────────────────────────────────────────
VIDEO_ID: str | None = "c8604c66-2a5d-4ce4-96b8-43186fad1e46"
INGEST_URL: str | None = None
STORAGE_ROOT = Path(__file__).parent.parent / "downloads"

def _print_section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")

def main() -> None:
    configure_debug_logging()
    
    _print_section("1. Index the video")
    service = RAGService()
    record = service.index_video(VIDEO_ID)
    print(f"Index status: {record.status}")
    print(f"Segments indexed: {record.segments_indexed}")
    
    # Needs a dummy project_id for search
    video = service.ingestion_db.get_video(VIDEO_ID)
    if not video:
        print(f"Error: Video {VIDEO_ID} not found in DB.")
        return
        
    project_id = video.project_id
    
    _print_section("2. Mode 1 FETCH - MCU shots")
    res = service.search(
        project_id=project_id,
        filters=StructuralFilters(shot_type="MCU")
    )
    print(f"Total count: {res.total_count}")
    for seg in res.segments:
        print(f"  [{seg.timecode_start}] {seg.shot_type}: {seg.observable_summary[:60]}...")
        
    _print_section("3. Mode 1 COUNT - music present")
    res = service.search(
        project_id=project_id,
        filters=StructuralFilters(music_present=True),
        operation="COUNT"
    )
    print(f"Total count: {res.total_count}")
    
    _print_section("4. Mode 1 GROUP_BY - shot_type")
    res = service.search(
        project_id=project_id,
        filters=StructuralFilters(),
        operation="GROUP_BY",
        group_by_field="shot_type"
    )
    print(f"Group by data: {res.group_by_data}")
    
    _print_section("5. Mode 2 semantic - creator explaining what an AI agent does")
    res = service.search(
        project_id=project_id,
        nl_query="creator explaining what an AI agent does",
        top_k=3
    )
    for seg in res.segments:
        print(f"  [{seg.timecode_start}] Score: {seg.score:.3f} | {seg.transcript[:80]}...")
        
    _print_section("6. Mode 3 hybrid - speaker_visible + 'AI agent'")
    res = service.search(
        project_id=project_id,
        filters=StructuralFilters(speaker_visible=True),
        nl_query="AI agent",
        top_k=3
    )
    for seg in res.segments:
        print(f"  [{seg.timecode_start}] Score: {seg.score:.3f} | {seg.observable_summary[:80]}...")

if __name__ == "__main__":
    main()
