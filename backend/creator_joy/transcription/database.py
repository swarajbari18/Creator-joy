from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from creator_joy.transcription.models import TranscriptionRecord, TranscriptionStatus

logger = logging.getLogger(__name__)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class TranscriptionDatabase:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        logger.debug("Initializing transcription database at %s", database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        logger.debug("Creating transcriptions table if missing")
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS transcriptions (
                    id TEXT PRIMARY KEY,
                    video_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    transcription_path TEXT,
                    error_message TEXT,
                    gemini_model TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
                );
                """
            )

    def create_or_reset_transcription(self, video_id: str, gemini_model: str) -> TranscriptionRecord:
        now = utc_now()
        logger.debug("Registering transcription for video_id=%s", video_id)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM transcriptions WHERE video_id = ?",
                (video_id,),
            ).fetchone()
            if existing:
                transcription_id = existing["id"]
                logger.debug("Resetting existing transcription row id=%s for retry", transcription_id)
                connection.execute(
                    """
                    UPDATE transcriptions
                    SET status = ?,
                        error_message = NULL,
                        transcription_path = NULL,
                        gemini_model = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (TranscriptionStatus.PENDING.value, gemini_model, now, transcription_id),
                )
            else:
                transcription_id = str(uuid.uuid4())
                logger.debug("Creating new transcription row id=%s", transcription_id)
                connection.execute(
                    """
                    INSERT INTO transcriptions (id, video_id, status, gemini_model, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (transcription_id, video_id, TranscriptionStatus.PENDING.value, gemini_model, now, now),
                )
        record = self.get_transcription(transcription_id)
        if record is None:
            raise RuntimeError(f"Transcription was inserted but could not be loaded: {transcription_id}")
        return record

    def update_transcription_status(
        self,
        transcription_id: str,
        status: TranscriptionStatus,
        transcription_path: str | None = None,
        error_message: str | None = None,
    ) -> None:
        logger.debug(
            "Updating transcription status id=%s status=%s",
            transcription_id,
            status.value,
        )
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE transcriptions
                SET status = ?, transcription_path = ?, error_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (status.value, transcription_path, error_message, utc_now(), transcription_id),
            )

    def get_transcription(self, transcription_id: str) -> TranscriptionRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM transcriptions WHERE id = ?",
                (transcription_id,),
            ).fetchone()
        return self._transcription_from_row(row) if row else None

    def get_transcription_for_video(self, video_id: str) -> TranscriptionRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM transcriptions WHERE video_id = ? ORDER BY created_at DESC LIMIT 1",
                (video_id,),
            ).fetchone()
        return self._transcription_from_row(row) if row else None

    @staticmethod
    def _transcription_from_row(row: sqlite3.Row) -> TranscriptionRecord:
        return TranscriptionRecord(
            id=row["id"],
            video_id=row["video_id"],
            status=TranscriptionStatus(row["status"]),
            transcription_path=row["transcription_path"],
            error_message=row["error_message"],
            gemini_model=row["gemini_model"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
