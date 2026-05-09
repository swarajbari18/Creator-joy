import sqlite3
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from langchain_core.messages import HumanMessage, AIMessage


class ChatMemory:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.create_tables()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def create_tables(self) -> None:
        """Create chat_history table if not exists. Call at startup."""
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id  TEXT    NOT NULL,
                    session_id  TEXT    NOT NULL,
                    turn_number INTEGER NOT NULL,
                    role        TEXT    NOT NULL CHECK(role IN ('user', 'assistant', 'tool_call', 'tool_return')),
                    content     TEXT    NOT NULL,
                    skill_name  TEXT,   -- populated for tool_call rows only
                    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
                );
                CREATE INDEX IF NOT EXISTS idx_chat_history_session
                    ON chat_history(session_id, turn_number);
            """)

    def save_turn(
        self,
        project_id: str,
        session_id: str,
        turn_number: int,
        role: str,
        content: str,
        skill_name: str | None = None,
    ) -> None:
        """Persist one row. Call after each role event in a turn."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_history (project_id, session_id, turn_number, role, content, skill_name)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (project_id, session_id, turn_number, role, content, skill_name),
            )

    def load_history(
        self,
        session_id: str,
        max_turns: int = 15,
    ) -> list[dict]:
        """
        Return last max_turns turns as list of dicts with keys:
        turn_number, role, content, skill_name.
        Only returns 'user' and 'assistant' rows (not tool_call/tool_return) 
        for LangChain message injection.
        """
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT turn_number, role, content, skill_name
                FROM chat_history
                WHERE session_id = ? AND role IN ('user', 'assistant')
                ORDER BY turn_number DESC, id DESC
                LIMIT ?
                """,
                (session_id, max_turns * 2),  # max_turns is pairs of user/assistant
            ).fetchall()
        
        # Reverse to get chronological order
        history = [dict(row) for row in reversed(rows)]
        return history

    async def compact_if_needed(
        self,
        session_id: str,
        threshold_turns: int = 20,
        keep_recent: int = 10,
        llm: Any = None,
    ) -> None:
        """
        If session has > threshold_turns, summarize the oldest turns using
        a cheap LLM call and replace them with a single 'assistant' row
        containing the summary. Keeps the most recent keep_recent turns intact.
        """
        with self._connect() as connection:
            total_turns = connection.execute(
                "SELECT COUNT(DISTINCT turn_number) as count FROM chat_history WHERE session_id = ?",
                (session_id,)
            ).fetchone()["count"]
            
            if total_turns <= threshold_turns:
                return

            # Implementation of compaction would go here.
            # 1. Fetch turns to summarize (total_turns - keep_recent)
            # 2. Call LLM to summarize
            # 3. Delete old turns
            # 4. Insert summary turn
            # For now, following the plan's instruction to provide this API.
            pass


def build_message_history(history: list[dict]) -> list:
    """Convert SQLite rows to LangChain message objects."""
    messages = []
    for row in history:
        if row["role"] == "user":
            messages.append(HumanMessage(content=row["content"]))
        elif row["role"] == "assistant":
            messages.append(AIMessage(content=row["content"]))
    return messages
