from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class VideoStatus(StrEnum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"


class VideoFileKind(StrEnum):
    VIDEO = "video"
    AUDIO = "audio"
    METADATA = "metadata"
    THUMBNAIL = "thumbnail"
    OTHER = "other"


@dataclass(frozen=True)
class ProjectRecord:
    id: str
    name: str
    description: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class VideoRecord:
    id: str
    project_id: str
    source_url: str
    normalized_url: str
    platform: str | None
    yt_dlp_id: str | None
    title: str | None
    uploader: str | None
    duration: float | None
    upload_date: str | None
    status: VideoStatus
    error_message: str | None
    metadata_path: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class VideoFileRecord:
    id: str
    video_id: str
    kind: VideoFileKind
    path: str
    ext: str | None
    size_bytes: int | None
    created_at: str


@dataclass(frozen=True)
class DownloadedArtifacts:
    metadata: dict[str, Any]
    video_paths: list[Path] = field(default_factory=list)
    audio_paths: list[Path] = field(default_factory=list)
    thumbnail_paths: list[Path] = field(default_factory=list)


@dataclass(frozen=True)
class IngestionSettings:
    storage_root: Path = Path("storage")
    database_filename: str = "creator_joy.sqlite3"
    video_merge_format: str = "mp4"
    audio_codec: str = "mp3"
    audio_quality: str = "192"
    ytdlp_quiet: bool = True
    ytdlp_no_warnings: bool = False

    @property
    def database_path(self) -> Path:
        return self.storage_root / self.database_filename
