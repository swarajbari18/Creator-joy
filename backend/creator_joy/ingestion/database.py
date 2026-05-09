from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from creator_joy.ingestion.models import (
    ProjectRecord,
    VideoFileKind,
    VideoFileRecord,
    VideoRecord,
    VideoStatus,
)

logger = logging.getLogger(__name__)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class IngestionDatabase:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        logger.debug("Initializing ingestion database at %s", database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        logger.debug("Creating ingestion tables if missing")
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS videos (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    normalized_url TEXT NOT NULL,
                    platform TEXT,
                    yt_dlp_id TEXT,
                    title TEXT,
                    uploader TEXT,
                    duration REAL,
                    upload_date TEXT,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    metadata_path TEXT,
                    role TEXT,
                    engagement_metrics TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    UNIQUE(project_id, normalized_url)
                );

                CREATE TABLE IF NOT EXISTS video_files (
                    id TEXT PRIMARY KEY,
                    video_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    path TEXT NOT NULL,
                    ext TEXT,
                    size_bytes INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
                );
                """
            )
            # Migrate columns added after initial schema creation.
            # ALTER TABLE ignores columns that already exist via the except below.
            for col_def in ("role TEXT", "engagement_metrics TEXT"):
                col_name = col_def.split()[0]
                try:
                    connection.execute(f"ALTER TABLE videos ADD COLUMN {col_def}")
                    logger.debug("Migrated videos table: added column %s", col_name)
                except Exception:
                    pass  # column already present

    def create_project(self, name: str, description: str | None = None) -> ProjectRecord:
        project_id = str(uuid.uuid4())
        now = utc_now()
        logger.debug("Creating project id=%s name=%s", project_id, name)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO projects (id, name, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (project_id, name, description, now, now),
            )
        project = self.get_project(project_id)
        if project is None:
            raise RuntimeError(f"Project was inserted but could not be loaded: {project_id}")
        return project

    def get_project(self, project_id: str) -> ProjectRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return self._project_from_row(row) if row else None

    def list_projects(self) -> list[ProjectRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM projects ORDER BY created_at ASC"
            ).fetchall()
        return [self._project_from_row(row) for row in rows]

    def create_or_reset_video(self, project_id: str, source_url: str) -> VideoRecord:
        normalized_url = self.normalize_url(source_url)
        now = utc_now()
        logger.debug(
            "Registering URL for ingestion project_id=%s normalized_url=%s",
            project_id,
            normalized_url,
        )
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT * FROM videos
                WHERE project_id = ? AND normalized_url = ?
                """,
                (project_id, normalized_url),
            ).fetchone()
            if existing:
                video_id = existing["id"]
                logger.debug("Resetting existing video row id=%s for retry", video_id)
                connection.execute("DELETE FROM video_files WHERE video_id = ?", (video_id,))
                connection.execute(
                    """
                    UPDATE videos
                    SET source_url = ?,
                        status = ?,
                        error_message = NULL,
                        metadata_path = NULL,
                        platform = NULL,
                        yt_dlp_id = NULL,
                        title = NULL,
                        uploader = NULL,
                        duration = NULL,
                        upload_date = NULL,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (source_url, VideoStatus.PENDING.value, now, video_id),
                )
            else:
                video_id = str(uuid.uuid4())
                logger.debug("Creating new video row id=%s", video_id)
                connection.execute(
                    """
                    INSERT INTO videos (
                        id, project_id, source_url, normalized_url, status,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        video_id,
                        project_id,
                        source_url,
                        normalized_url,
                        VideoStatus.PENDING.value,
                        now,
                        now,
                    ),
                )
        video = self.get_video(video_id)
        if video is None:
            raise RuntimeError(f"Video was inserted but could not be loaded: {video_id}")
        return video

    def update_video_status(
        self,
        video_id: str,
        status: VideoStatus,
        error_message: str | None = None,
    ) -> None:
        logger.debug("Updating video status video_id=%s status=%s", video_id, status.value)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE videos
                SET status = ?, error_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (status.value, error_message, utc_now(), video_id),
            )

    def update_video_metadata(
        self,
        video_id: str,
        metadata: dict,
        metadata_path: Path,
    ) -> None:
        logger.debug("Updating searchable metadata columns video_id=%s", video_id)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE videos
                SET platform = ?,
                    yt_dlp_id = ?,
                    title = ?,
                    uploader = ?,
                    duration = ?,
                    upload_date = ?,
                    metadata_path = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    metadata.get("extractor_key") or metadata.get("extractor"),
                    metadata.get("id"),
                    metadata.get("title"),
                    metadata.get("uploader") or metadata.get("channel"),
                    metadata.get("duration"),
                    metadata.get("upload_date"),
                    str(metadata_path),
                    utc_now(),
                    video_id,
                ),
            )

    def add_video_file(self, video_id: str, kind: VideoFileKind, path: Path) -> VideoFileRecord:
        file_id = str(uuid.uuid4())
        size_bytes = path.stat().st_size if path.exists() else None
        ext = path.suffix.lstrip(".") or None
        logger.debug(
            "Registering file video_id=%s kind=%s path=%s size_bytes=%s",
            video_id,
            kind.value,
            path,
            size_bytes,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO video_files (id, video_id, kind, path, ext, size_bytes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (file_id, video_id, kind.value, str(path), ext, size_bytes, utc_now()),
            )
        record = self.get_video_file(file_id)
        if record is None:
            raise RuntimeError(f"Video file was inserted but could not be loaded: {file_id}")
        return record

    def update_video_engagement(self, video_id: str, engagement_metrics_json: str) -> None:
        logger.debug("Updating engagement metrics video_id=%s", video_id)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE videos
                SET engagement_metrics = ?, updated_at = ?
                WHERE id = ?
                """,
                (engagement_metrics_json, utc_now(), video_id),
            )

    def update_video_role(self, video_id: str, role: str) -> None:
        logger.debug("Updating video role video_id=%s role=%s", video_id, role)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE videos
                SET role = ?, updated_at = ?
                WHERE id = ?
                """,
                (role, utc_now(), video_id),
            )

    def get_video(self, video_id: str) -> VideoRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM videos WHERE id = ?",
                (video_id,),
            ).fetchone()
        return self._video_from_row(row) if row else None

    def list_project_videos(self, project_id: str) -> list[VideoRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM videos
                WHERE project_id = ?
                ORDER BY created_at ASC
                """,
                (project_id,),
            ).fetchall()
        return [self._video_from_row(row) for row in rows]

    def get_video_file(self, file_id: str) -> VideoFileRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM video_files WHERE id = ?",
                (file_id,),
            ).fetchone()
        return self._video_file_from_row(row) if row else None

    def list_video_files(self, video_id: str) -> list[VideoFileRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM video_files
                WHERE video_id = ?
                ORDER BY created_at ASC
                """,
                (video_id,),
            ).fetchall()
        return [self._video_file_from_row(row) for row in rows]

    @staticmethod
    def normalize_url(url: str) -> str:
        return url.strip()

    @staticmethod
    def _project_from_row(row: sqlite3.Row) -> ProjectRecord:
        return ProjectRecord(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _video_from_row(row: sqlite3.Row) -> VideoRecord:
        return VideoRecord(
            id=row["id"],
            project_id=row["project_id"],
            source_url=row["source_url"],
            normalized_url=row["normalized_url"],
            platform=row["platform"],
            yt_dlp_id=row["yt_dlp_id"],
            title=row["title"],
            uploader=row["uploader"],
            duration=row["duration"],
            upload_date=row["upload_date"],
            status=VideoStatus(row["status"]),
            error_message=row["error_message"],
            metadata_path=row["metadata_path"],
            role=row["role"],
            engagement_metrics=row["engagement_metrics"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _video_file_from_row(row: sqlite3.Row) -> VideoFileRecord:
        return VideoFileRecord(
            id=row["id"],
            video_id=row["video_id"],
            kind=VideoFileKind(row["kind"]),
            path=row["path"],
            ext=row["ext"],
            size_bytes=row["size_bytes"],
            created_at=row["created_at"],
        )

