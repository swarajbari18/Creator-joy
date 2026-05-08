from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class TranscriptionStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class TranscriptionRecord:
    id: str
    video_id: str
    status: TranscriptionStatus
    transcription_path: str | None
    error_message: str | None
    gemini_model: str | None
    created_at: str
    updated_at: str


def _default_gemini_model() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")


@dataclass(frozen=True)
class TranscriptionSettings:
    storage_root: Path = field(default_factory=lambda: Path("downloads"))
    database_filename: str = "creator_joy.sqlite3"
    gemini_model: str = field(default_factory=_default_gemini_model)
    temperature: float = 0.1
    file_poll_interval_seconds: int = 5
    file_poll_timeout_seconds: int = 300

    @property
    def database_path(self) -> Path:
        return self.storage_root / self.database_filename
