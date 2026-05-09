"""
End-to-end chat service test.

Usage:
    cd backend
    export $(grep -v '^#' .env | xargs)
    python -m tests.dev_test_chat

Requires the ingestion + RAG pipeline to have been run first (dev_test_rag.py).
The project and video IDs below come from that run.
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid

from creator_joy.ingestion.logging_config import configure_debug_logging
from creator_joy.chat.service import ChatService
from creator_joy.rag.models import RAGSettings

# ── Configuration ─────────────────────────────────────────────────────────────
PROJECT_ID = "fdb0d91b-8e8e-4fe3-87ff-1fc4fc89ffde"
DB_PATH = RAGSettings().database_path

# Turn 1 — HookDiagnosis (pre_injected): first 30s breakdown
# Turn 2 — orchestrator answers directly (no analytics data)
# Turn 3 — EditingAnalysis (dynamic): cut rate, shot distribution
# Turn 4 — ScriptAnalysis (dynamic): verbatim transcript at a timecode
# Turn 5 — ProductionAudit (dynamic): lighting, mic, audio quality sample
TURNS = [
    "Analyse the hook in the AI agents explained video.",
    "What does the retention curve look like for that same video?",
    "What is the editing pace of the AI agents explained video? Give me cuts per minute and the shot type breakdown.",
    "Give me the verbatim transcript from 0:30 to 1:00 of the AI agents explained video.",
    "Audit the production quality of the AI agents explained video — lighting, microphone type, and audio quality.",
]

# ── Helpers ───────────────────────────────────────────────────────────────────


def _print_section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


async def run_turn(service: ChatService, session_id: str, turn: int, message: str) -> None:
    _print_section(f"Turn {turn}: {message!r}")

    full_response = ""
    async for event in service.stream_response(
        project_id=PROJECT_ID,
        session_id=session_id,
        user_message=message,
    ):
        etype = event.get("type")
        if etype == "token":
            chunk = event["content"]
            full_response += chunk
            print(chunk, end="", flush=True)
        elif etype == "skill_start":
            print(f"\n[skill → {event['skill']}]", flush=True)
        elif etype == "skill_complete":
            print(f"[skill ✓ {event['skill']}]", flush=True)
        elif etype == "skill_error":
            print(f"\n[skill ERROR {event['skill']}: {event.get('error')}]", flush=True)
        elif etype == "done":
            print()  # newline after streamed tokens


async def main() -> None:
    configure_debug_logging()

    service = ChatService(db_path=DB_PATH)
    session_id = f"dev-test-{uuid.uuid4().hex[:8]}"
    print(f"Session: {session_id}")
    print(f"Project: {PROJECT_ID}")

    for i, message in enumerate(TURNS, start=1):
        await run_turn(service, session_id, i, message)

    _print_section("History check")
    history = service.memory.load_history(session_id)
    print(f"Rows in memory: {len(history)}")
    for row in history:
        preview = row["content"][:80].replace("\n", " ")
        print(f"  [{row['role']:>10}] turn={row['turn_number']} | {preview}...")


if __name__ == "__main__":
    asyncio.run(main())
