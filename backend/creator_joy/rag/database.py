from __future__ import annotations
import logging, sqlite3, uuid
from datetime import UTC, datetime
from pathlib import Path

from creator_joy.rag.models import IndexRecord, IndexStatus

logger = logging.getLogger(__name__)

def utc_now() -> str:
    return datetime.now(UTC).isoformat()

class RAGDatabase:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        logger.debug("Initializing RAG database at %s", database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS rag_index (
                    id TEXT PRIMARY KEY,
                    video_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    segments_indexed INTEGER,
                    qdrant_collection TEXT NOT NULL,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
                );
            """)

    def create_or_reset_index(
        self,
        video_id: str,
        project_id: str,
        collection_name: str,
    ) -> IndexRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM rag_index WHERE video_id = ?", (video_id,)
            ).fetchone()
            if row:
                record_id = row["id"]
                connection.execute(
                    """
                    UPDATE rag_index
                    SET status = ?, segments_indexed = NULL, error_message = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (IndexStatus.PENDING.value, utc_now(), record_id)
                )
            else:
                record_id = str(uuid.uuid4())
                now = utc_now()
                connection.execute(
                    """
                    INSERT INTO rag_index (
                        id, video_id, project_id, status, segments_indexed,
                        qdrant_collection, error_message, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record_id, video_id, project_id, IndexStatus.PENDING.value,
                        None, collection_name, None, now, now
                    )
                )
            connection.commit()
            return self.get_index(record_id)  # type: ignore

    def update_index_status(
        self,
        record_id: str,
        status: IndexStatus,
        segments_indexed: int | None = None,
        error_message: str | None = None
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE rag_index
                SET status = ?, segments_indexed = ?, error_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (status.value, segments_indexed, error_message, utc_now(), record_id)
            )
            connection.commit()

    def get_index(self, record_id: str) -> IndexRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM rag_index WHERE id = ?", (record_id,)
            ).fetchone()
            if not row:
                return None
            return IndexRecord(
                id=row["id"],
                video_id=row["video_id"],
                project_id=row["project_id"],
                status=IndexStatus(row["status"]),
                segments_indexed=row["segments_indexed"],
                qdrant_collection=row["qdrant_collection"],
                error_message=row["error_message"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
