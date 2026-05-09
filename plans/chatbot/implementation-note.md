# Chatbot Implementation Note

This document details the implementation of the CreatorJoy Chatbot system, following the 100-day brainstormed implementation plan.

## Architecture Overview

The chatbot is built as a multi-agent system using **LangGraph** and **LangChain**, orchestrated by a main agent (the "Orchestrator") and 14 specialized sub-agents (the "Skills").

### Data Flow

1.  **Ingestion & Engagement:**
    *   During video ingestion, `VideoIngestionService` now calls the `engagement` module.
    *   `engagement/calculator.py` computes metrics like `er_views`, `er_followers`, `velocity`, etc., from yt-dlp metadata.
    *   These metrics are stored as a JSON blob in the `engagement_metrics` column of the `videos` table in SQLite.
    *   Each video is also assigned a `role` ("creator" or "competitor") at ingestion time.

2.  **Chat Request Initialization:**
    *   The `ChatService` loads the project manifest and pre-computed engagement metrics from SQLite.
    *   `engagement/formatter.py` formats these metrics into a text block for the system prompt.
    *   `chat/prompts.py` assembles the Orchestrator's system prompt, including the manifest, metrics, and a catalog of available skills from `chat/registry.py`.
    *   Conversation history is loaded from the `chat_history` table via `ChatMemory` in `chat/memory.py`.

3.  **Orchestration Loop:**
    *   The Orchestrator agent (`chat/agent.py`) receives the system prompt, history, and user message.
    *   It can call `use_sub_agent_with_skill` to delegate tasks to sub-agents.
    *   Sub-agents are categorized into:
        *   `search`: Direct Qdrant access via `search_segments` tool.
        *   `pre_injected`: Data is pre-fetched and injected into the sub-agent's prompt (e.g., `HookDiagnosis`).
        *   `dynamic`: Sub-agent uses the `retrieve` tool, which itself calls the `search_skill` sub-agent internally.
    *   All sub-agents return structured JSON summaries to the Orchestrator to minimize context usage.

4.  **Streaming & Response:**
    *   The system uses Server-Sent Events (SSE) to stream tokens and "skill events" (start/complete) to the frontend.
    *   Final synthesized responses and tool interactions are persisted back to the `chat_history` table.

## Component Details

### 1. Engagement Module (`creator_joy/engagement/`)
*   **calculator.py:** Implements standard industry formulas for ER (views), ER (followers), like/comment rates, and engagement velocity.
*   **benchmarks.py:** Contains industry benchmarks for YouTube, TikTok, and Instagram, allowing the system to categorize performance (e.g., "excellent", "good").
*   **formatter.py:** Generates the "Video Analytics" section for the system prompt.

### 2. Chat Module (`creator_joy/chat/`)
*   **memory.py:** Manages SQLite-based conversation persistence. Implements history loading and future-proof compaction logic.
*   **tools.py:** Contains the `search_segments` tool (for Qdrant) and the `retrieve` tool (agent-to-agent). Includes a `SAMPLE` operation that distributes searches across a video's timeline.
*   **registry.py:** Central registry for all 14 skills, defining their descriptions, categories, and pre-fetch logic.
*   **agent.py:** Factory for creating sub-agents and the main orchestrator. Configures the LLM (Gemini 2.5 Flash) with specific parameters (`thinking_budget=0`, `temperature=1.0`).

### 3. API Layer (`api/`)
*   **main.py:** Entry point for the FastAPI application.
*   **routers/chat.py:** Implements the `/projects/{id}/chat` SSE endpoint and history retrieval.
*   **routers/projects.py** & **ingestion.py:** Basic management of projects and video ingestion with role support.

## Testing & Validation

### How to Test
1.  **Unit Tests:**
    *   Run tests for `engagement/calculator.py` with mock metadata.
    *   Verify `ChatMemory` can save and load history correctly.
2.  **Integration Tests:**
        cd backend
        export $(grep -v '^#' .env | xargs)
        uvicorn api.main:app
        python -m tests.dev_test_chat
3.  **End-to-End:**
    *   Ingest a video with a specific role.
    *   Trigger transcription and indexing.
    *   Ask the chatbot about the video and verify it calls the correct sub-agent (e.g., `HookDiagnosis`) and returns a cited response.

## Strategic Guardrails Implemented
*   **Context Efficiency:** Sub-agents return condensed summaries, not raw payloads.
*   **No Hallucinations:** Orchestrator is strictly bound to the provided video manifest.
*   **Cost Control:** Maximum of 3 sub-agent calls per turn.
*   **Arithmetic Integrity:** All engagement metrics are pre-computed; the LLM never performs raw math.
