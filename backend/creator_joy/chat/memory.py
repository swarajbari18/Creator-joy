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
                    role        TEXT    NOT NULL CHECK(role IN ('user', 'assistant', 'tool_call', 'tool_return', 'thought')),
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
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, turn_number, role, content, skill_name
                FROM chat_history
                WHERE session_id = ? AND role IN ('user', 'assistant', 'thought')
                ORDER BY turn_number DESC, id DESC
                LIMIT ?
                """,
                (session_id, max_turns * 20),
            ).fetchall()
        
        rows = [dict(row) for row in rows]
        
        # Group thoughts by turn_number and attach to the assistant message of that turn
        # When loading history, we ignore 'active' statuses to prevent duplicates and ghost rollers.
        history = []
        turn_to_thoughts = {}
        
        for row in rows:
            role = row["role"]
            tn = row["turn_number"]
            if role == "thought":
                try:
                    event = json.loads(row["content"])
                    # Skip 'active' states in history - we only care about 'complete' or 'error'
                    if event.get("status") == "active":
                        continue
                        
                    if tn not in turn_to_thoughts: turn_to_thoughts[tn] = []
                    turn_to_thoughts[tn].append(event)
                except: pass
            elif role in ("assistant", "user"):
                history.append(row)

        # Attach and reverse
        for row in history:
            if row["role"] == "assistant":
                thoughts = turn_to_thoughts.get(row["turn_number"], [])
                row["skillEvents"] = list(reversed(thoughts))

        return list(reversed(history))

    def list_sessions(self, project_id: str) -> list[dict]:
        """Return one entry per session with session_id, first user message, and last active time."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    session_id,
                    MIN(content) AS first_message, -- Simplest way: MIN on turn_number=1 message
                    MAX(created_at) AS last_active
                FROM chat_history
                WHERE project_id = ? AND turn_number = 1 AND role = 'user'
                GROUP BY session_id
                ORDER BY last_active DESC
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

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
