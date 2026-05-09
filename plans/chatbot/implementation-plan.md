# Chatbot Architecture Implementation Plan

**Date:** 2026-05-09  
**Depends on:** `ingestion/`, `transcription/`, `rag/` — all built and tested  
**Delivers:** Working streaming chatbot with multi-skill sub-agents, conversation memory, FastAPI backend

---

## What This Plan Covers

Everything from the current state (ingestion + transcription + RAG complete) to a production chatbot:

1. Engagement module
2. Chat history schema and memory management
3. Tools layer: `search_segments` (search skill only), `retrieve` (dynamic skills only), pre-injection (pre_injected skills)
4. Skill registry and loading
5. `use_sub_agent_with_skill` tool factory
6. System prompt assembly
7. Orchestrator agent
8. Streaming implementation
9. FastAPI backend
10. Build sequence

---

## 1. Folder Structure

All new code is in these two locations. Nothing in `ingestion/`, `transcription/`, or `rag/` is modified.

```
backend/creator_joy/
├── ingestion/          (existing — do not touch)
├── transcription/      (existing — do not touch)
├── rag/                (existing — do not touch)
│
├── engagement/         (NEW)
│   ├── __init__.py
│   ├── calculator.py
│   ├── benchmarks.py
│   └── formatter.py
│
├── chat/               (NEW)
│   ├── __init__.py
│   ├── models.py
│   ├── memory.py
│   ├── prompts.py
│   ├── registry.py
│   ├── tools.py
│   ├── agent.py
│   └── service.py
│
└── skills/             (skill.md = system prompt for that skill's sub-agent)
    ├── search_skill/   (existing — the retrieval agent; has search_segments tool)
    │   └── skill.md
    ├── HookDiagnosis/
    │   └── skill.md
    ├── TwoVideoComparison/
    │   └── skill.md
    ├── RetentionDiagnosis/
    │   └── skill.md
    ├── ScriptAnalysis/
    │   └── skill.md
    ├── SingleVideoAnalysis/
    │   └── skill.md
    ├── ProductionAudit/
    │   └── skill.md
    ├── EditingAnalysis/
    │   └── skill.md
    ├── CompetitorIntelligence/
    │   └── skill.md
    ├── SeriesAnalysis/
    │   └── skill.md
    ├── OverlayAudit/
    │   └── skill.md
    ├── AudioAnalysis/
    │   └── skill.md
    ├── EngagementCorrelation/
    │   └── skill.md
    └── ShortFormOptimization/
        └── skill.md

backend/api/            (NEW)
├── __init__.py
├── main.py
├── models.py
└── routers/
    ├── projects.py
    ├── ingestion.py
    └── chat.py
```

---

## 2. Engagement Module (`backend/creator_joy/engagement/`)

This module pre-computes all engagement metrics from `metadata.json` (yt-dlp output). These computed values are stored in SQLite and injected into the main agent's system prompt at session start. The LLM never computes arithmetic from raw counts — a critical failure mode identified in `docs/chatbot-design-simulation.md` Simulation 1.

### `engagement/calculator.py`

Implements the exact formulas from `docs/engagement-rate-research.md` Section 3. No new research needed — copy the Python code directly from that document.

Exports: `compute_all_engagement_metrics(metadata: dict) -> dict`

Returns a dict with these keys (all `float | None`):
- `er_views` — `(likes + comments) / views × 100` — PRIMARY metric
- `er_followers` — `(likes + comments) / followers × 100` — secondary
- `like_rate` — `likes / views × 100`
- `comment_rate` — `comments / views × 100`
- `like_to_comment_ratio` — `likes / comments`
- `er_per_minute` — `er_views / (duration / 60)`
- `views_per_minute` — `views / (duration / 60)`
- `engagement_velocity` — `(likes + comments) / days_since_upload`
- `heatmap_peak_intensity` — `max(heatmap[].value)` when heatmap is not None
- `heatmap_avg_intensity` — mean of heatmap values
- Raw pass-throughs: `view_count`, `like_count`, `comment_count`, `channel_follower_count`, `duration_seconds`, `video_age_days`

All functions are None-safe: missing raw fields return None for dependent metrics. Never raise on missing data.

### `engagement/benchmarks.py`

Contains the `BENCHMARKS` dict from `docs/engagement-rate-research.md` Section 8.3. Copy it verbatim.

Exports:
- `get_tier(follower_count: int | None, platform: str) -> str | None`
- `benchmark_comparison(er_views: float, follower_count: int | None, platform: str) -> dict`

### `engagement/formatter.py`

Exports: `format_metrics_for_system_prompt(videos: list[dict]) -> str`

Takes a list of video dicts (each containing engagement metrics + metadata) and returns the formatted block that gets injected into the orchestrator's system prompt. Format:

```
## Video Analytics

VIDEO A — "How I Built My Audience" (YOUR VIDEO)
  Views: 12,400 | Likes: 310 | Comments: 89 | Duration: 8:12
  ER (views): 3.22% | Tier: micro | Assessment: good (median 3.74%)
  Follower base: 8,200 | Uploaded: 2026-03-14 (56 days ago)
  Heatmap peak: 0.78 at 3:24

VIDEO B — "I Went From 0 to 100k" (COMPETITOR VIDEO)
  Views: 47,300 | Likes: 2,180 | Comments: 412 | Duration: 12:07
  ER (views): 5.47% | Tier: micro | Assessment: excellent (median 3.74%)
  Follower base: 8,200 | Uploaded: 2026-02-28 (70 days ago)
  Heatmap peak: not available
```

Key fields: all pre-computed ER values, tier label, assessment label, duration formatted as MM:SS, video_age_days computed fresh at session init (not cached from SQLite).

### `engagement/__init__.py`

Exports: `compute_all_engagement_metrics`, `format_metrics_for_system_prompt`, `benchmark_comparison`

### Integration with existing SQLite

Add an `engagement_metrics` TEXT column (JSON blob) to the `videos` table in SQLite. Compute and store at ingestion completion time. The engagement module is called from `IngestionService` after `metadata.json` is written.

This makes engagement data available without re-reading the metadata file on every chat request.

---

## 3. Conversation Memory (`backend/creator_joy/chat/memory.py`)

### SQLite Schema

Add a `chat_history` table to the existing `creator_joy.sqlite3`:

```sql
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
```

### What Gets Stored

| Role | Content | Notes |
|---|---|---|
| `user` | user message text | raw |
| `assistant` | final synthesized response text | only what user sees |
| `tool_call` | JSON: `{"skill_name": "...", "situational_prompt": "..."}` | for debugging/audit |
| `tool_return` | sub-agent's synthesized response text | NOT raw Qdrant payloads |

What is NEVER stored: sub-agent internal tool calls, raw Qdrant segment payloads, reranker intermediate results, sub-agent intermediate reasoning steps.

This decision follows `docs/chatbot-design-simulation.md` Gap 4 research: raw Qdrant payloads inflate context window dramatically over long conversations. The synthesized response is 95% smaller and contains all the information the main agent needs on future turns.

### `memory.py` Public API

```python
class ChatMemory:
    def __init__(self, db_path: str): ...
    
    def create_tables(self) -> None:
        """Create chat_history table if not exists. Call at startup."""
    
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
    
    def compact_if_needed(
        self,
        session_id: str,
        threshold_turns: int = 20,
        keep_recent: int = 10,
        llm,
    ) -> None:
        """
        If session has > threshold_turns, summarize the oldest turns using
        a cheap LLM call and replace them with a single 'assistant' row
        containing the summary. Keeps the most recent keep_recent turns intact.
        """
```

### History Injection into Orchestrator

Before each orchestrator invocation, load history and convert:

```python
def build_message_history(history: list[dict]) -> list:
    """Convert SQLite rows to LangChain message objects."""
    messages = []
    for row in history:
        if row["role"] == "user":
            messages.append(HumanMessage(content=row["content"]))
        elif row["role"] == "assistant":
            messages.append(AIMessage(content=row["content"]))
    return messages
```

The full message list for the orchestrator is:
```
[SystemMessage(system_prompt), *history_messages, HumanMessage(current_user_message)]
```

---

## 4. Tools Layer (`backend/creator_joy/chat/tools.py`)

Three categories of sub-agent get three different tool setups:

| Category | Skills | Tools given |
|---|---|---|
| `search` | `search_skill` | `[search_segments]` — direct Qdrant access |
| `pre_injected` | `HookDiagnosis`, `OverlayAudit` | `[]` — data arrives pre-fetched in human message |
| `dynamic` | all other 11 skills | `[retrieve]` — calls search_skill sub-agent internally |

The `search_segments` tool is **only ever given to the search skill agent**. Specialized skill agents never see Qdrant directly.

### `SubAgentContext` Dataclass

```python
from dataclasses import dataclass

@dataclass
class SubAgentContext:
    project_id: str
    video_ids: list[str]   # all video IDs in this project
    skill_prompt: str       # contents of the skill.md file (loaded at factory time)
```

This is passed to `create_react_agent` as `context_schema` and auto-injected into tool functions via `ToolRuntime`.

### Tool A: `search_segments` (search skill only)

```python
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from typing import Optional

class SearchArgs(BaseModel):
    """Arguments for searching video segments."""
    nl_query: Optional[str] = Field(
        default=None,
        description=(
            "Natural language query for semantic search. "
            "Use when looking for meaning, tone, visual style, or content themes. "
            "Leave None for structural queries (counts, filters, group-by)."
        )
    )
    operation: str = Field(
        description=(
            "What to do with results. One of: "
            "FETCH (return matching segments with all fields), "
            "COUNT (return integer count only), "
            "SUM_duration (return total seconds of matching segments), "
            "GROUP_BY (return field-value distribution — requires group_by_field), "
            "SAMPLE (return N segments distributed across video timeline — requires top_k)."
        )
    )
    video_id: Optional[str] = Field(
        default=None,
        description=(
            "UUID of a specific video to search. "
            "Leave None to search all videos in the current project. "
            "Use the video UUIDs from the Available Videos section of your instructions."
        )
    )
    shot_type: Optional[str] = Field(
        default=None,
        description="Filter to segments with this shot type. E.g. 'MCU', 'B-roll', 'CU', 'WS'."
    )
    cut_type: Optional[str] = Field(
        default=None,
        description="Filter to segments with this cut type. E.g. 'jump-cut', 'hard-cut', 'dissolve'."
    )
    speaker_visible: Optional[bool] = Field(
        default=None,
        description="True to filter to segments where the speaker is visible on camera."
    )
    music_present: Optional[bool] = Field(
        default=None,
        description="True to filter to segments with music. False for silence."
    )
    timecode_start_max_seconds: Optional[float] = Field(
        default=None,
        description="Only include segments that START before this many seconds into the video."
    )
    timecode_start_min_seconds: Optional[float] = Field(
        default=None,
        description="Only include segments that START after this many seconds into the video."
    )
    group_by_field: Optional[str] = Field(
        default=None,
        description="Field name to group by. Required for GROUP_BY operation. E.g. 'shot_type', 'cut_type', 'camera_angle'."
    )
    top_k: int = Field(
        default=10,
        description="Max number of segments to return for FETCH and SAMPLE operations. Use larger values for SAMPLE to get better coverage."
    )

@tool(args_schema=SearchArgs)
def search_segments(
    nl_query: Optional[str] = None,
    operation: str = "FETCH",
    video_id: Optional[str] = None,
    shot_type: Optional[str] = None,
    cut_type: Optional[str] = None,
    speaker_visible: Optional[bool] = None,
    music_present: Optional[bool] = None,
    timecode_start_max_seconds: Optional[float] = None,
    timecode_start_min_seconds: Optional[float] = None,
    group_by_field: Optional[str] = None,
    top_k: int = 10,
    runtime: ToolRuntime = None,
) -> str:
    """
    Search video segments from the Qdrant vector database.
    
    Returns segment data for the current project. Use FETCH to retrieve segments
    with full field payloads. Use COUNT/GROUP_BY for aggregate queries.
    Use SAMPLE to get representative segments from beginning, middle, and end.
    
    The project_id and video_ids are automatically scoped to the current session —
    you do not need to provide them.
    """
    project_id = runtime.context.project_id
    scoped_video_ids = [video_id] if video_id else runtime.context.video_ids
    
    from creator_joy.rag import RAGService, StructuralFilters
    from creator_joy.rag.models import RAGSettings
    
    rag = RAGService(RAGSettings())
    
    filters = None
    if any([shot_type, cut_type, speaker_visible is not None, music_present is not None,
            timecode_start_max_seconds, timecode_start_min_seconds]):
        filters = StructuralFilters(
            shot_type=shot_type,
            cut_type=cut_type,
            speaker_visible=speaker_visible,
            music_present=music_present,
            timecode_start_max_seconds=timecode_start_max_seconds,
            timecode_start_min_seconds=timecode_start_min_seconds,
        )
    
    # SAMPLE operation: distribute top_k evenly across video timeline
    if operation == "SAMPLE":
        return _sample_segments(rag, project_id, scoped_video_ids, top_k, filters)
    
    result = rag.search(
        project_id=project_id,
        video_ids=scoped_video_ids,
        filters=filters,
        nl_query=nl_query,
        operation=operation,
        group_by_field=group_by_field,
        top_k=top_k,
    )
    return _format_search_result(result, operation)
```

### SAMPLE Operation Implementation

`_sample_segments()` divides the video into `top_k` equal time windows and fetches the first segment from each window. This enables ProductionAudit and SeriesAnalysis to get representative coverage without fetching all segments.

Implementation: get total duration from SQLite `videos` table, divide into `top_k` buckets, run `top_k` separate structural FETCH calls each with a timecode window of `[bucket_start, bucket_start + window_size]`, limit=1. Concatenate results.

This needs `SUM_duration` to be called first on the video to get total duration, or the duration can be retrieved from the `videos` SQLite table directly by `project_id + video_id`.

### `_format_search_result()` — Critical Design Decision

The sub-agent must return a structured summary, NOT raw Qdrant payloads. This is the fix for Gap 7 from `docs/chatbot-design-simulation.md`: raw payloads can be 15,000-30,000 tokens; structured summaries are ~200 tokens.

The formatter condenses segment results into:
```json
{
  "query_executed": {
    "mode": "structural|semantic|hybrid",
    "operation": "FETCH",
    "video_id": "uuid-A",
    "filters_applied": {"shot_type": "MCU", "timecode_start_max_seconds": 30.0}
  },
  "result_count": 4,
  "timecode_range": "0:00 - 0:31",
  "segments": [
    {
      "segment_id": 1,
      "timecode": "0:00-0:08",
      "shot_type": "MCU",
      "camera_angle": "eye-level",
      "transcript": "Hey everyone, so today I want to talk about...",
      "on_screen_text": [],
      "cut_type": null,
      "music_present": false,
      "key_light_direction": "left",
      "audio_quality": "clean-studio",
      "microphone_type": "lav"
    }
  ],
  "aggregates": {
    "shot_type_counts": {"MCU": 3, "B-roll": 1},
    "music_present_count": 0,
    "cut_events": [{"segment_id": 2, "timecode": "0:08", "cut_type": "hard-cut"}],
    "on_screen_text_timeline": [
      {"segment_id": 2, "timecode": "0:08", "text": "3 YEARS OF RESEARCH", "position": "center"}
    ]
  }
}
```

For COUNT: return `{"count": 23, "query": "cut_type=jump-cut, video=uuid-A"}`.
For GROUP_BY: return `{"field": "shot_type", "distribution": {"MCU": 38, "B-roll": 17, "CU": 14}}`.

Return as a JSON string (safe for LangChain tool return type).

### Tool B: `retrieve(prompt: str)` (Category `dynamic` skills only)

```python
@tool
async def retrieve(prompt: str, runtime: ToolRuntime = None) -> str:
    """
    Retrieve video segment data by describing what you need in plain English.
    
    Examples of good prompts:
      "Get the cut type distribution across all segments of video UUID-A"
      "Fetch segments from video UUID-B where timecode_start < 30 seconds, include transcript and shot_type"
      "Count jump cuts in video UUID-A"
    
    Returns structured segment data with segment_id and timecode citations.
    """
    from creator_joy.chat.registry import SKILLS
    from langgraph.prebuilt import create_react_agent
    
    skill = SKILLS["search_skill"]
    search_context = SubAgentContext(
        project_id=runtime.context.project_id,
        video_ids=runtime.context.video_ids,
        skill_prompt=skill.prompt,
    )
    search_agent = create_react_agent(
        model=_make_sub_agent_llm(),
        tools=[search_segments],
        context_schema=SubAgentContext,
        prompt=lambda state, rt: [SystemMessage(content=rt.context.skill_prompt)],
    )
    result = await search_agent.ainvoke(
        {"messages": [HumanMessage(content=prompt)]},
        context=search_context,
        config={"recursion_limit": 10},
    )
    return result["messages"][-1].content
```

This tool is the same `use_sub_agent_with_skill` mechanism, hardcoded to `search_skill`. The specialized skill writes plain English — the search skill decides Mode 1/2/3 and which filters to apply. The specialized skill never touches `search_segments`, field names, or Qdrant.

### Category A: Pre-Injection (no tool)

For `HookDiagnosis` and `OverlayAudit`, the retrieval scope is fully known before the skill runs. The `make_skill_tool` factory fetches the data directly from `RAGService` and injects it into the human message before creating the agent. The skill agent receives all data in context and needs no tool.

Pre-fetch logic per skill:
- `HookDiagnosis`: `rag.search(project_id, video_ids, filters=StructuralFilters(timecode_start_max_seconds=30.0), operation="FETCH", top_k=20)` — formatted result appended to human message
- `OverlayAudit`: `rag.search(project_id, video_ids, operation="FETCH", top_k=300)` — all segments fetched, skill extracts overlay entries from payload

The `Skill` dataclass carries a `prefetch_fn` field for these skills (see registry).

---

## 5. Skill Registry (`backend/creator_joy/chat/registry.py`)

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable, Awaitable

SKILLS_DIR = Path(__file__).parent.parent / "skills"

@dataclass
class Skill:
    name: str
    description: str        # 1-2 sentences for orchestrator system prompt
    when_to_use: str        # trigger conditions for orchestrator
    prompt_path: Path
    category: str           # "search" | "pre_injected" | "dynamic"
    prefetch_fn: Optional[Callable] = None  # only for "pre_injected" skills
    _prompt_cache: str | None = field(default=None, repr=False)
    
    @property
    def prompt(self) -> str:
        if not self._prompt_cache:
            self._prompt_cache = self.prompt_path.read_text()
        return self._prompt_cache

# search_skill + 13 specialized skills
# search_skill is callable by the orchestrator directly AND used internally by retrieve() tool
SKILLS: dict[str, Skill] = {
    "search_skill": Skill(
        name="search_skill",
        description="Queries the video segment database directly. Use for simple retrieval: counting, distributions, timecode lookups, or any question answerable with raw data.",
        when_to_use="Use when the question is a direct data lookup: counts, field distributions, timecode lookups, or any query that doesn't require domain analysis.",
        prompt_path=SKILLS_DIR / "search_skill" / "skill.md",
        category="search",
    ),
    "HookDiagnosis": Skill(
        name="HookDiagnosis",
        description="Analyzes the first 30 seconds of a video: opening line, shot type, text overlays, music, camera angle, pattern interrupt.",
        when_to_use="Use when the question involves hooks, intros, openings, first impressions, or the first 30 seconds.",
        prompt_path=SKILLS_DIR / "HookDiagnosis" / "skill.md",
        category="pre_injected",
        prefetch_fn=_hook_prefetch,   # see below
    ),
    "TwoVideoComparison": Skill(
        name="TwoVideoComparison",
        description="Retrieves the same field(s) from two videos and returns a side-by-side comparison. Never compares asymmetrically.",
        when_to_use='Use when the user explicitly or implicitly references two videos ("my video vs competitor\'s", "compare", "what are they doing that I\'m not").',
        prompt_path=SKILLS_DIR / "TwoVideoComparison" / "skill.md",
        category="dynamic",
    ),
    "RetentionDiagnosis": Skill(
        name="RetentionDiagnosis",
        description="Retrieves what was happening at a specific timecode to diagnose a retention drop: transcript, shot type, music state, topic transition.",
        when_to_use='Use when the question is about why viewers left at a specific moment ("drop at 3:24", "retention dip", "why did viewers leave").',
        prompt_path=SKILLS_DIR / "RetentionDiagnosis" / "skill.md",
        category="dynamic",
    ),
    "ScriptAnalysis": Skill(
        name="ScriptAnalysis",
        description="Retrieves verbatim transcript text. Never paraphrases. Returns exact words spoken with segment_id and timecode.",
        when_to_use='Use when the user wants exact quotes, transcript, verbatim text, or what was said at a specific moment.',
        prompt_path=SKILLS_DIR / "ScriptAnalysis" / "skill.md",
        category="dynamic",
    ),
    "SingleVideoAnalysis": Skill(
        name="SingleVideoAnalysis",
        description="Default workhorse for any single-video question that doesn't fit a more specific skill. Every claim cites segment_id and timecode.",
        when_to_use="Use when the question is about one specific video and no other skill matches more precisely.",
        prompt_path=SKILLS_DIR / "SingleVideoAnalysis" / "skill.md",
        category="dynamic",
    ),
    "ProductionAudit": Skill(
        name="ProductionAudit",
        description="Samples representative segments (beginning, middle, end) to assess lighting, audio, camera, background, color grade, and mic type.",
        when_to_use='Use when the question is about production quality, lighting, audio, camera setup, mic, background, or "how professional does this look".',
        prompt_path=SKILLS_DIR / "ProductionAudit" / "skill.md",
        category="dynamic",
    ),
    "EditingAnalysis": Skill(
        name="EditingAnalysis",
        description="Analyzes editing rhythm: cuts per minute, cut type distribution, transition inventory, B-roll distribution, shot type variation.",
        when_to_use='Use when the question is about pacing, editing style, cuts, transitions, rhythm, or B-roll usage.',
        prompt_path=SKILLS_DIR / "EditingAnalysis" / "skill.md",
        category="dynamic",
    ),
    "CompetitorIntelligence": Skill(
        name="CompetitorIntelligence",
        description="Extracts recurring patterns from competitor videos — what they consistently do, not pairwise comparison to the creator's video.",
        when_to_use='Use when the question is about a competitor\'s strategy, signature style, or patterns across their videos (without explicit comparison to the creator\'s own video).',
        prompt_path=SKILLS_DIR / "CompetitorIntelligence" / "skill.md",
        category="dynamic",
    ),
    "SeriesAnalysis": Skill(
        name="SeriesAnalysis",
        description="Finds patterns across multiple of the creator's own videos — what is stable, what has changed, what correlates with better performance.",
        when_to_use='Use when the question spans multiple of the creator\'s own videos ("across my last 10 videos", "what do my best videos have in common", "has my style changed").',
        prompt_path=SKILLS_DIR / "SeriesAnalysis" / "skill.md",
        category="dynamic",
    ),
    "OverlayAudit": Skill(
        name="OverlayAudit",
        description="Returns a complete chronological inventory of every text overlay, graphic, and animation in a video. Never samples — always complete.",
        when_to_use='Use when the question is specifically about text overlays, graphics, lower-thirds, or on-screen visual elements.',
        prompt_path=SKILLS_DIR / "OverlayAudit" / "skill.md",
        category="pre_injected",
        prefetch_fn=_overlay_prefetch,   # see below
    ),
    "AudioAnalysis": Skill(
        name="AudioAnalysis",
        description="Analyzes music genre distribution, music change events with timecodes, sound effects, and audio quality across a video.",
        when_to_use='Use when the question is about music, sound, audio, soundtrack, or audio quality.',
        prompt_path=SKILLS_DIR / "AudioAnalysis" / "skill.md",
        category="dynamic",
    ),
    "EngagementCorrelation": Skill(
        name="EngagementCorrelation",
        description="Surfaces observable correlations between production choices and engagement data. NEVER asserts causation — only observable patterns.",
        when_to_use='Use when the question connects video content to performance ("why did this video get more views", "what did my top-performing videos have in common").',
        prompt_path=SKILLS_DIR / "EngagementCorrelation" / "skill.md",
        category="dynamic",
    ),
    "ShortFormOptimization": Skill(
        name="ShortFormOptimization",
        description="Specialized analysis for short-form content (< 60 seconds): 3-second hook window, completion-rate signals, platform-specific audio.",
        when_to_use='Use when the question is specifically about Shorts, Reels, TikTok, or vertical video under 60 seconds.',
        prompt_path=SKILLS_DIR / "ShortFormOptimization" / "skill.md",
        category="dynamic",
    ),
}
```

### Pre-Fetch Functions (for `pre_injected` skills)

These live in `registry.py` above the `SKILLS` dict.

```python
async def _hook_prefetch(project_id: str, video_ids: list[str], situational_prompt: str) -> str:
    """Pre-fetch first 30 seconds for HookDiagnosis. Called by factory before agent creation."""
    from creator_joy.rag import RAGService, StructuralFilters
    from creator_joy.rag.models import RAGSettings
    from creator_joy.chat.tools import _format_search_result
    rag = RAGService(RAGSettings())
    result = rag.search(
        project_id=project_id,
        video_ids=video_ids,
        filters=StructuralFilters(timecode_start_max_seconds=30.0),
        operation="FETCH",
        top_k=20,
    )
    return _format_search_result(result, "FETCH")

async def _overlay_prefetch(project_id: str, video_ids: list[str], situational_prompt: str) -> str:
    """Pre-fetch all segments for OverlayAudit. Skill extracts overlay entries from payload."""
    from creator_joy.rag import RAGService
    from creator_joy.rag.models import RAGSettings
    from creator_joy.chat.tools import _format_search_result
    rag = RAGService(RAGSettings())
    result = rag.search(
        project_id=project_id,
        video_ids=video_ids,
        operation="FETCH",
        top_k=300,   # fetch all segments — overlay audit must be complete
    )
    return _format_search_result(result, "FETCH")

def build_skills_catalog() -> str:
    """Return the skills section for the orchestrator system prompt."""
    lines = ["## Available Skills\n"]
    for skill in SKILLS.values():
        lines.append(f"### {skill.name}")
        lines.append(f"**What it does:** {skill.description}")
        lines.append(f"**Use when:** {skill.when_to_use}\n")
    return "\n".join(lines)
```

---

## 6. System Prompt Assembly (`backend/creator_joy/chat/prompts.py`)

The orchestrator's system prompt is assembled fresh at session start. It is NOT cached across sessions because engagement metrics are video-specific.

### `build_orchestrator_system_prompt(project_manifest, engagement_block) -> str`

The prompt has five sections in this order:

```
SECTION 1: Role and Operating Rules
SECTION 2: Video Manifest (explicit labeled list of ingested videos)
SECTION 3: Engagement Metrics (pre-computed per video)
SECTION 4: Available Skills (catalog from registry)
SECTION 5: Orchestration Rules (how to use use_sub_agent_with_skill + guardrails)
```

### Section 1 — Role and Operating Rules

```
You are CreatorJoy, a video analysis assistant for content creators. You answer questions
about creator and competitor videos by delegating to specialist sub-agents that retrieve
data from a structured database of video segments.

Operating rules:
- You answer only about videos listed in the Available Videos section below.
- If the user references a video not in that list, do NOT call any sub-agent.
  Tell them the video is not yet ingested and explain how to add it.
- If the user's question does not specify which video or which dimension to analyze,
  ask EXACTLY ONE clarifying question and wait for the response before calling any sub-agent.
- You may call use_sub_agent_with_skill at most 3 times per user message.
  If you believe you need more, tell the user what you found so far and ask if they want
  to continue with the rest in the next message.
- Never invent data. If a sub-agent returns no results, report that clearly.
```

### Section 2 — Video Manifest

```
## Available Videos

The following videos are available for analysis. Reference video UUIDs exactly as listed
when writing situational prompts to sub-agents.

VIDEO UUID: {video_id_A}
  Title: "How I Built My Audience"
  Creator: YourChannel
  Role: YOUR VIDEO
  Platform: youtube
  URL: https://youtube.com/watch?v=...

VIDEO UUID: {video_id_B}
  Title: "I Went From 0 to 100k"
  Creator: CompetitorChannel
  Role: COMPETITOR VIDEO
  Platform: youtube
  URL: https://youtube.com/watch?v=...
```

The role field (YOUR VIDEO / COMPETITOR VIDEO) is set by the project's ingestion metadata. When a project is created via the API, the caller labels each URL as creator or competitor. This label is stored in SQLite `videos` table and injected here.

### Section 3 — Engagement Metrics

Injected via `format_metrics_for_system_prompt()` from the engagement module. Pre-computed values only — no raw counts for the LLM to compute from.

### Section 4 — Available Skills

Injected via `build_skills_catalog()` from the registry.

### Section 5 — Orchestration Rules

```
## How to Use Skills

When you call use_sub_agent_with_skill, write a situational prompt that contains:
- **User goal**: what the creator ultimately wants to understand
- **Prior findings** (if any): distilled, max 3 bullet points, not raw data
- **Current task**: exactly what to find NOW — specific fields, timecodes, or operations
- **Video UUIDs in scope**: list the exact UUIDs from the Available Videos section
- **Why this call**: what decision you will make with the returned data

A good situational prompt (example):
"User goal: understand why March videos underperformed.
Prior findings: engagement data shows ER dropped from 5.2% to 2.1% in March videos.
Current task: fetch hook segments (timecode < 30s) from VIDEO UUID abc123. Get shot_type,
transcript, on_screen_text, cut_type, music_present fields.
Why: compare hook structure to earlier high-performing videos."

A bad situational prompt:
"Find info about the hook."

## Ambiguity Rule
If the user's question does not specify:
  (a) which video to analyze, OR
  (b) which dimension (production, editing, content, engagement)
Then ask EXACTLY ONE clarifying question before calling any sub-agent.
Format: "To help you best, could you tell me: [single question with a list of choices]?"

## Call Limit
Maximum 3 sub-agent calls per user message. If you reach this limit,
tell the user what you found so far and offer to continue in the next message.
```

---

## 7. `use_sub_agent_with_skill` Tool Factory (`backend/creator_joy/chat/agent.py`)

### Tool Definition

```python
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from langchain_google_genai import ChatGoogleGenerativeAI

class SubAgentCallArgs(BaseModel):
    skill_name: str = Field(
        description=(
            "Name of the skill to invoke. Available skills: "
            "search_skill (direct data retrieval), "
            "HookDiagnosis, TwoVideoComparison, RetentionDiagnosis, ScriptAnalysis, "
            "SingleVideoAnalysis, ProductionAudit, EditingAnalysis, CompetitorIntelligence, "
            "SeriesAnalysis, OverlayAudit, AudioAnalysis, EngagementCorrelation, "
            "ShortFormOptimization."
        )
    )
    situational_prompt: str = Field(
        description=(
            "Detailed briefing for the sub-agent. Must include: user goal, "
            "prior findings (distilled), current specific task, video UUIDs in scope, "
            "and why this sub-agent is being called. Do NOT include expected output format."
        )
    )
```

### Tool Factory

`project_id` and `video_ids` are bound via closure — the LLM never passes them, they are never in the LangChain tool schema.

The factory creates one `retrieve` tool instance (shared by all `dynamic` skill agents in this session) and routes each `use_sub_agent_with_skill` call to the correct agent setup based on `skill.category`.

```python
def make_skill_tool(project_id: str, video_ids: list[str]):
    """
    Returns the use_sub_agent_with_skill tool bound to the current session context.
    Called once per session during orchestrator initialization.
    """
    from creator_joy.chat.tools import search_segments, retrieve as _retrieve_template, SubAgentContext
    
    # Build the retrieve tool for dynamic skills.
    # ToolRuntime auto-injects project_id/video_ids into retrieve() at call time.
    retrieve_tool = _retrieve_template  # retrieve is defined in tools.py; SubAgentContext injected via ToolRuntime
    
    @tool(args_schema=SubAgentCallArgs)
    async def use_sub_agent_with_skill(skill_name: str, situational_prompt: str) -> str:
        """
        Delegate a specific sub-task to a specialized skill sub-agent.
        Always provide a complete situational_prompt with user goal, video UUIDs in scope,
        prior findings (if any), and the specific task for this call.
        """
        from creator_joy.chat.registry import SKILLS
        from langgraph.config import get_stream_writer
        
        if skill_name not in SKILLS:
            return f"Error: unknown skill '{skill_name}'. Available: {list(SKILLS.keys())}"
        
        skill = SKILLS[skill_name]
        stream_writer = get_stream_writer()
        stream_writer({"type": "skill_start", "skill": skill_name,
                       "message": f"Using {skill_name}..."})
        
        context = SubAgentContext(
            project_id=project_id,
            video_ids=video_ids,
            skill_prompt=skill.prompt,
        )
        
        try:
            if skill.category == "search":
                # search_skill: direct access to search_segments
                agent = create_react_agent(
                    model=_make_sub_agent_llm(),
                    tools=[search_segments],
                    context_schema=SubAgentContext,
                    prompt=lambda state, rt: [SystemMessage(content=rt.context.skill_prompt)],
                )
                result = await agent.ainvoke(
                    {"messages": [HumanMessage(content=situational_prompt)]},
                    context=context,
                    config={"recursion_limit": 10},
                )
            
            elif skill.category == "pre_injected":
                # Pre-fetch data from RAGService, inject into human message. No tools for the skill agent.
                pre_fetched = await skill.prefetch_fn(project_id, video_ids, situational_prompt)
                enriched_message = (
                    f"{situational_prompt}\n\n"
                    f"--- PRE-FETCHED SEGMENT DATA ---\n"
                    f"{pre_fetched}"
                )
                agent = create_react_agent(
                    model=_make_sub_agent_llm(),
                    tools=[],
                    context_schema=SubAgentContext,
                    prompt=lambda state, rt: [SystemMessage(content=rt.context.skill_prompt)],
                )
                result = await agent.ainvoke(
                    {"messages": [HumanMessage(content=enriched_message)]},
                    context=context,
                    config={"recursion_limit": 10},
                )
            
            else:  # skill.category == "dynamic"
                # Specialized skill with retrieve tool. retrieve() calls search_skill internally.
                agent = create_react_agent(
                    model=_make_sub_agent_llm(),
                    tools=[retrieve_tool],
                    context_schema=SubAgentContext,
                    prompt=lambda state, rt: [SystemMessage(content=rt.context.skill_prompt)],
                )
                result = await agent.ainvoke(
                    {"messages": [HumanMessage(content=situational_prompt)]},
                    context=context,
                    config={"recursion_limit": 10},
                )
            
            output = result["messages"][-1].content
            stream_writer({"type": "skill_complete", "skill": skill_name})
            return output
        
        except Exception as e:
            stream_writer({"type": "skill_error", "skill": skill_name, "error": str(e)})
            return f"Skill '{skill_name}' encountered an error: {str(e)}"
    
    return use_sub_agent_with_skill
```

### LLM Configuration

```python
def _make_orchestrator_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=1.0,
        thinking_budget=0,
        max_output_tokens=8192,
        max_retries=3,
        disable_streaming="tool_calling",  # invoke() during tool steps, stream() for final
    )

def _make_sub_agent_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=1.0,
        thinking_budget=0,
        max_output_tokens=4096,
        max_retries=2,
    )
```

`thinking_budget=0` is non-negotiable — avoids the `thought_signature` bug documented in `docs/gemini-tool-calling-research.md` Section 4.9. `temperature=1.0` is required for Gemini 2.5 Flash to avoid looping behavior documented in Section 6.

### Orchestrator Agent Factory

```python
def create_orchestrator(
    project_id: str,
    video_ids: list[str],
    system_prompt: str,
) -> CompiledGraph:
    """
    Create the main orchestrator agent for a session.
    Called once per chat request (lightweight — LLM inference dominates init cost).
    """
    skill_tool = make_skill_tool(project_id, video_ids)
    llm = _make_orchestrator_llm()
    
    return create_react_agent(
        model=llm,
        tools=[skill_tool],
        prompt=system_prompt,
    )
```

Note: `create_react_agent` is used (not a compiled subgraph) because the orchestrator has exactly one tool and doesn't need the complexity of a full state graph. The `create_react_agent` from `langgraph.prebuilt` handles the ReAct loop correctly with Gemini and sets `ToolMessage.name` properly (fixing bug 4.4 from the research doc).

---

## 8. Streaming Implementation (`backend/creator_joy/chat/service.py`)

### `ChatService` — The Main Coordinator

```python
class ChatService:
    def __init__(self, db_path: str):
        self.memory = ChatMemory(db_path)
        self.ingestion_db = IngestionDatabase(db_path)
    
    async def stream_response(
        self,
        project_id: str,
        session_id: str,
        user_message: str,
    ):
        """
        Async generator yielding SSE event dicts.
        Called by the FastAPI endpoint.
        """
        # 1. Load video manifest for this project
        videos = self.ingestion_db.get_project_videos(project_id)
        video_ids = [v.id for v in videos]
        
        # 2. Load engagement metrics (pre-computed in SQLite)
        engagement_data = self._load_engagement_data(videos)
        
        # 3. Build system prompt
        from creator_joy.engagement.formatter import format_metrics_for_system_prompt
        from creator_joy.chat.prompts import build_orchestrator_system_prompt
        engagement_block = format_metrics_for_system_prompt(engagement_data)
        system_prompt = build_orchestrator_system_prompt(
            project_manifest=videos,
            engagement_block=engagement_block,
        )
        
        # 4. Load conversation history
        history = self.memory.load_history(session_id, max_turns=15)
        history_messages = build_message_history(history)
        
        # 5. Persist user message
        turn_number = len(history) // 2 + 1
        self.memory.save_turn(project_id, session_id, turn_number, "user", user_message)
        
        # 6. Create orchestrator for this session
        from creator_joy.chat.agent import create_orchestrator
        orchestrator = create_orchestrator(project_id, video_ids, system_prompt)
        
        # 7. Build full message list for this invocation
        messages = history_messages + [HumanMessage(content=user_message)]
        
        # 8. Stream events
        full_response = ""
        tool_calls_this_turn = []
        
        async for event in orchestrator.astream_events(
            {"messages": messages},
            version="v2",
        ):
            event_type = event["event"]
            
            if event_type == "on_custom_event":
                # Events from get_stream_writer() inside tools
                data = event["data"]
                yield data
            
            elif event_type == "on_chat_model_stream":
                # Final synthesis tokens — only stream if no tool call pending
                chunk = event["data"]["chunk"]
                if chunk.content and not _is_tool_call_chunk(chunk):
                    full_response += chunk.content
                    yield {"type": "token", "content": chunk.content}
            
            elif event_type == "on_tool_start":
                if event["name"] == "use_sub_agent_with_skill":
                    inputs = event["data"]["input"]
                    tool_calls_this_turn.append(inputs)
            
            elif event_type == "on_tool_end":
                if event["name"] == "use_sub_agent_with_skill":
                    # Persist tool_call and tool_return to SQLite
                    call_data = tool_calls_this_turn[-1] if tool_calls_this_turn else {}
                    self.memory.save_turn(
                        project_id, session_id, turn_number, "tool_call",
                        json.dumps(call_data),
                        skill_name=call_data.get("skill_name"),
                    )
                    self.memory.save_turn(
                        project_id, session_id, turn_number, "tool_return",
                        str(event["data"]["output"]),
                    )
        
        # 9. Persist final synthesized response
        if full_response:
            self.memory.save_turn(
                project_id, session_id, turn_number, "assistant", full_response
            )
        
        # 10. Compact memory if needed
        await self.memory.compact_if_needed(
            session_id, threshold_turns=20, keep_recent=10, llm=_make_orchestrator_llm()
        )
        
        yield {"type": "done"}
```

### Streaming Pattern Details

The `disable_streaming="tool_calling"` param on `ChatGoogleGenerativeAI` automatically:
- Uses `invoke()` internally when tool calls are made (avoiding the chunk-delivery bug in `docs/gemini-tool-calling-research.md` Section 5)
- Uses `stream()` for the final synthesis (where no tools are called)

`astream_events(version="v2")` at the outer orchestrator level captures all events including custom events from `get_stream_writer()` calls inside `use_sub_agent_with_skill`.

The result: users see `skill_start` events immediately when a tool is called, then the sub-agent executes silently, then `skill_complete` fires, and finally the synthesis streams token by token.

---

## 9. FastAPI Backend (`backend/api/`)

### `api/main.py`

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import projects, ingestion, chat

app = FastAPI(title="CreatorJoy API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(projects.router, prefix="/projects", tags=["projects"])
app.include_router(ingestion.router, prefix="/projects", tags=["ingestion"])
app.include_router(chat.router, prefix="/projects", tags=["chat"])
```

### Endpoint List

| Method | Path | Description |
|---|---|---|
| POST | `/projects` | Create a new project |
| GET | `/projects/{project_id}` | Get project details |
| POST | `/projects/{project_id}/ingest` | Ingest one or more video URLs |
| POST | `/projects/{project_id}/videos/{video_id}/transcribe` | Trigger transcription |
| POST | `/projects/{project_id}/videos/{video_id}/index` | Trigger RAG indexing |
| GET | `/projects/{project_id}/videos` | List videos with engagement metrics |
| POST | `/projects/{project_id}/chat` | Streaming chat (SSE) |
| GET | `/projects/{project_id}/chat/sessions/{session_id}/history` | Get chat history |

### `api/models.py` — Request/Response Schemas

```python
from pydantic import BaseModel
from typing import Optional

class CreateProjectRequest(BaseModel):
    name: str

class IngestRequest(BaseModel):
    urls: list[str]
    roles: list[str]  # "creator" or "competitor" — one per URL

class ChatRequest(BaseModel):
    session_id: str
    message: str

class VideoResponse(BaseModel):
    id: str
    url: str
    title: str
    role: str
    status: str
    er_views: Optional[float]
    view_count: Optional[int]
    duration_seconds: Optional[int]
```

### `api/routers/chat.py` — SSE Endpoint

```python
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import json

router = APIRouter()

@router.post("/{project_id}/chat")
async def chat_stream(project_id: str, request: ChatRequest):
    from creator_joy.chat.service import ChatService
    service = ChatService(db_path=DB_PATH)
    
    async def event_generator():
        async for event in service.stream_response(
            project_id=project_id,
            session_id=request.session_id,
            user_message=request.message,
        ):
            yield f"data: {json.dumps(event)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",      # disable nginx buffering
            "Connection": "keep-alive",
        },
    )
```

### SSE Event Types (Frontend Contract)

| Type | Payload | Meaning |
|---|---|---|
| `skill_start` | `{skill: "HookDiagnosis", message: "..."}` | Sub-agent is starting |
| `skill_complete` | `{skill: "HookDiagnosis"}` | Sub-agent finished |
| `skill_error` | `{skill: "...", error: "..."}` | Sub-agent failed |
| `token` | `{content: "abc"}` | Final synthesis token |
| `done` | `{}` | Stream complete |

---

## 10. Integration Points

### How chatbot calls into existing services

- `ChatService` → `IngestionDatabase` (read project videos, get engagement data)
- `use_sub_agent_with_skill` → `search_segments` tool → `RAGService.search()`
- `ChatService` → `ChatMemory` (SQLite read/write for conversation history)
- `engagement/calculator.py` called from `IngestionService.ingest_urls()` after metadata.json write

No changes to `IngestionService`, `TranscriptionService`, or `RAGService` internals. The engagement module adds a post-ingestion compute step but does not modify the existing call flow.

### `IngestionService` integration point

After `metadata.json` is written and the video record is saved to SQLite, add:

```python
# In ingestion/service.py, after successful download
from creator_joy.engagement import compute_all_engagement_metrics
metrics = compute_all_engagement_metrics(metadata_dict)
self.db.update_video_engagement(video_record.id, json.dumps(metrics))
```

This requires adding `update_video_engagement()` to `IngestionDatabase` and an `engagement_metrics` TEXT column to the `videos` table.

---

## 11. Build Sequence

Build in this exact order. Each step is testable independently before proceeding.

### Step 1: Engagement Module
**Files:** `engagement/calculator.py`, `engagement/benchmarks.py`, `engagement/formatter.py`  
**Test:** Unit test `compute_all_engagement_metrics()` with sample `metadata.json` from `downloads/`. Verify all None-handling.

### Step 2: SQLite Schema Updates
**Files:** Add `engagement_metrics` column to `videos`, create `chat_history` table  
**Test:** `ALTER TABLE` runs without error; `chat_history` table exists with correct schema.

### Step 3: Chat Memory Module
**Files:** `chat/memory.py`  
**Test:** Write user + assistant rows; load back; verify compaction trigger.

### Step 4: Tools Layer
**Files:** `chat/tools.py` (SubAgentContext, SearchArgs, search_segments, retrieve, _format_search_result, _sample_segments)  
**Tests:**
- Call `search_segments` directly with a SubAgentContext fixture → verify Qdrant returns and _format_search_result output
- Call `retrieve("Count jump cuts in video UUID-X")` with a SubAgentContext fixture → verify it spins up search_skill sub-agent and returns structured data
Requires Qdrant running with indexed test data from `dev_test_rag.py`.

### Step 5: Skill Registry
**Files:** `chat/registry.py`, `skills/search_skill/skill.md` (already exists), create stubs for 13 skills  
**Test:** `SKILLS["HookDiagnosis"].prompt` returns non-empty string; `SKILLS["search_skill"].category == "search"`; `build_skills_catalog()` includes search_skill in output.

### Step 6: Orchestrator System Prompt Builder
**Files:** `chat/prompts.py`  
**Test:** Call `build_orchestrator_system_prompt()` with fixture videos; verify all sections present.

### Step 7: `use_sub_agent_with_skill` Tool Factory
**Files:** `chat/agent.py` (tool factory + LLM config + orchestrator factory)  
**Test:** Invoke the tool directly (bypass main agent) with a real `situational_prompt`. Verify sub-agent calls `search_segments` and returns a text response.

### Step 8: Chat Service (Non-Streaming)
**Files:** `chat/service.py` (invoke-only version first, no streaming)  
**Test:** `dev_test_chat.py` — create project, ingest video, run a simple chat turn. Verify SQLite records created.

### Step 9: FastAPI Backend (Non-Streaming Endpoints)
**Files:** `api/main.py`, `api/models.py`, `api/routers/projects.py`, `api/routers/ingestion.py`  
**Test:** `uvicorn api.main:app`, POST to `/projects`, POST to `/projects/{id}/ingest`. Verify responses.

### Step 10: Streaming (SSE)
**Files:** Update `chat/service.py` to use `astream_events`, `api/routers/chat.py`  
**Test:** `curl -N -X POST localhost:8000/projects/{id}/chat -H "Content-Type: application/json" -d '{"session_id":"test","message":"How many jump cuts does my video have?"}'`. Verify SSE stream with `skill_start`, `token`, `done` events.

### Step 11: Skill Files (real content)
After Step 10 is working, replace skill.md stubs with real content per Plan 2. This is safe because skill.md is loaded at runtime — no code changes needed.

---

## Key Architectural Guardrails (from simulation research)

These specific constraints must be wired in, not left to LLM judgment:

1. **Video manifest guard (P0):** The orchestrator system prompt includes ALL ingested video UUIDs. The prompt instructs: "If user references a video not in this list, do NOT call any sub-agent." This is the circuit breaker for hallucinated video analysis.

2. **Ambiguity rule (P0):** System prompt mandates ONE clarifying question before sub-agent calls on underspecified queries. This prevents expensive multi-skill blasts for vague questions.

3. **3-call cap (P1):** System prompt states max 3 sub-agent calls per turn. The LangGraph agent config enforces this with `max_iterations=3` on the tool node (or manual tracking via sub-agent call counter in session state).

4. **No arithmetic by LLM (P1):** All ER values, duration, tier assessments are pre-computed and injected. LLM reads values, never calculates them.

5. **Synthesized responses only in SQLite (P1):** `ChatMemory` stores only final `assistant` text, not raw Qdrant payloads. This is enforced by what `ChatService` passes to `memory.save_turn()`.

6. **Creator vs. competitor labeling (P1):** The video manifest in the system prompt explicitly labels each video as "YOUR VIDEO" or "COMPETITOR VIDEO". This is set at project creation time and stored in SQLite.
