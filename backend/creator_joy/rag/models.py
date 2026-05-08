from __future__ import annotations
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
import os

class IndexStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass(frozen=True)
class IndexRecord:
    id: str
    video_id: str
    project_id: str
    status: IndexStatus
    segments_indexed: int | None
    qdrant_collection: str
    error_message: str | None
    created_at: str
    updated_at: str

def _env_str(key: str, default: str) -> str:
    return os.environ.get(key, default)

def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    return int(val) if val else default

@dataclass(frozen=True)
class RAGSettings:
    storage_root: Path = field(default_factory=lambda: Path("downloads"))
    database_filename: str = "creator_joy.sqlite3"
    qdrant_host: str = field(default_factory=lambda: _env_str("QDRANT_HOST", "localhost"))
    qdrant_port: int = field(default_factory=lambda: _env_int("QDRANT_PORT", 6333))
    collection_name: str = "video_segments"
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    sparse_model: str = "Qdrant/minicoil-v1"
    reranker_model: str = "Qwen/Qwen3-Reranker-0.6B"
    embedding_dim: int = 4096
    use_gpu: bool = True
    use_contextual_prefix: bool = False
    prefetch_k: int = 50
    rerank_top_n: int = 10

    @property
    def database_path(self) -> Path:
        return self.storage_root / self.database_filename

@dataclass
class StructuralFilters:
    """All None by default. Set only the fields you want to filter on."""
    # Keyword filters (exact match)
    shot_type: str | None = None
    camera_angle: str | None = None
    camera_movement: str | None = None
    depth_of_field: str | None = None
    background_type: str | None = None
    key_light_direction: str | None = None
    light_quality: str | None = None
    color_temperature_feel: str | None = None
    music_genre_feel: str | None = None
    music_tempo_feel: str | None = None
    audio_quality: str | None = None
    color_grade_feel: str | None = None
    language: str | None = None
    speaker_id: str | None = None
    cut_type: str | None = None

    # Boolean filters
    speaker_visible: bool | None = None
    music_present: bool | None = None
    on_screen_text_present: bool | None = None
    graphics_present: bool | None = None
    cut_occurred: bool | None = None
    catch_light_in_eyes: bool | None = None

    # Range filters
    duration_min_seconds: float | None = None
    duration_max_seconds: float | None = None
    timecode_start_min_seconds: float | None = None
    timecode_start_max_seconds: float | None = None

    # Multi-value filters (match ANY)
    video_ids: list[str] | None = None  # additional per-segment video filter

@dataclass(frozen=True)
class SegmentResult:
    point_id: str
    score: float
    video_id: str
    project_id: str
    segment_id: int
    timecode_start: str
    timecode_end: str
    transcript: str
    observable_summary: str
    shot_type: str
    payload: dict  # full payload for downstream use

@dataclass(frozen=True)
class SearchResult:
    mode: str          # "structural" | "semantic" | "hybrid"
    operation: str     # "FETCH" | "COUNT" | "SUM_duration" | "GROUP_BY"
    total_count: int
    segments: list[SegmentResult]
    group_by_data: dict | None  # populated when operation="GROUP_BY"

    def to_dict(self) -> dict:
        """LangChain tool compatibility."""
        return {
            "mode": self.mode,
            "operation": self.operation,
            "total_count": self.total_count,
            "segments": [
                {
                    "point_id": s.point_id,
                    "score": s.score,
                    "video_id": s.video_id,
                    "segment_id": s.segment_id,
                    "timecode_start": s.timecode_start,
                    "timecode_end": s.timecode_end,
                    "transcript": s.transcript,
                    "observable_summary": s.observable_summary,
                    "shot_type": s.shot_type,
                }
                for s in self.segments
            ],
            "group_by_data": self.group_by_data,
        }
