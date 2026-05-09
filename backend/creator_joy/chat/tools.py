import json
from dataclasses import dataclass
from typing import Optional, Any
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import ToolRuntime


@dataclass
class SubAgentContext:
    project_id: str
    video_ids: list[str]   # all video IDs in this project
    skill_prompt: str       # contents of the skill.md file


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
        description="Max number of segments to return for FETCH and SAMPLE operations."
    )


class RetrieveArgs(BaseModel):
    prompt: str = Field(description="Plain English description of what segment data you need.")


def _format_search_result(result: Any, operation: str) -> str:
    """Condenses segment results into a structured summary to save context tokens."""
    if operation == "COUNT":
        return json.dumps({"count": getattr(result, "total_count", 0)})

    if operation == "GROUP_BY":
        return json.dumps({
            "distribution": getattr(result, "group_by_data", {})
        })

    if operation == "SUM_duration":
        return json.dumps({"total_duration_seconds": getattr(result, "sum_duration", 0)})

    # FETCH or SAMPLE — pull extra fields from payload since SegmentResult
    # only exposes top-level fields (shot_type, transcript, etc.); the rest live in payload.
    segments = []
    on_screen_text_timeline = []
    shot_types: dict[str, int] = {}

    for s in getattr(result, "segments", []):
        p = s.payload if hasattr(s, "payload") and s.payload else {}
        segments.append({
            "segment_id": s.segment_id,
            "timecode": f"{s.timecode_start}-{s.timecode_end}",
            "shot_type": s.shot_type,
            "camera_angle": p.get("camera_angle"),
            "transcript": s.transcript,
            "on_screen_text": p.get("on_screen_text"),
            "cut_type": p.get("cut_type"),
            "music_present": p.get("music_present"),
            "audio_quality": p.get("audio_quality"),
            "microphone_type": p.get("microphone_type"),
        })
        shot_types[s.shot_type or "unknown"] = shot_types.get(s.shot_type or "unknown", 0) + 1
        if p.get("on_screen_text"):
            on_screen_text_timeline.append({
                "segment_id": s.segment_id,
                "timecode": s.timecode_start,
                "text": p["on_screen_text"],
            })

    return json.dumps({
        "result_count": len(segments),
        "segments": segments,
        "aggregates": {
            "shot_type_counts": shot_types,
            "on_screen_text_timeline": on_screen_text_timeline,
        },
    })


def _sample_segments(rag: Any, project_id: str, video_ids: list[str], top_k: int, filters: Any) -> str:
    from creator_joy.ingestion.database import IngestionDatabase
    from creator_joy.ingestion.models import IngestionSettings
    from creator_joy.rag.models import StructuralFilters

    db = IngestionDatabase(IngestionSettings().database_path)
    all_segments = []

    for v_id in video_ids:
        video = db.get_video(v_id)
        if not video or not video.duration:
            continue

        duration = video.duration
        window_size = duration / top_k

        for i in range(top_k):
            start = i * window_size
            end = start + window_size
            window_filters = StructuralFilters(
                timecode_start_min_seconds=start,
                timecode_start_max_seconds=end,
            )
            res = rag.search(
                project_id=project_id,
                video_ids=[v_id],
                filters=window_filters,
                operation="FETCH",
                top_k=1,
            )
            if res.segments:
                all_segments.extend(res.segments)

    class _MockResult:
        def __init__(self, segments):
            self.segments = segments

    return _format_search_result(_MockResult(all_segments), "FETCH")


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
    """Search video segments from the Qdrant vector database."""
    from creator_joy.rag import RAGService, StructuralFilters
    from creator_joy.rag.models import RAGSettings

    ctx: SubAgentContext = runtime.context
    project_id = ctx.project_id
    scoped_video_ids = [video_id] if video_id else ctx.video_ids

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


@tool(args_schema=RetrieveArgs)
async def retrieve(prompt: str, runtime: ToolRuntime = None) -> str:
    """Retrieve video segment data by describing what you need in plain English."""
    from creator_joy.chat.registry import SKILLS
    from langgraph.prebuilt import create_react_agent
    from creator_joy.chat.agent import _make_sub_agent_llm

    ctx: SubAgentContext = runtime.context
    skill = SKILLS["search_skill"]
    search_context = SubAgentContext(
        project_id=ctx.project_id,
        video_ids=ctx.video_ids,
        skill_prompt=skill.prompt,
    )

    search_agent = create_react_agent(
        model=_make_sub_agent_llm(),
        tools=[search_segments],
        prompt=skill.prompt,
        context_schema=SubAgentContext,
    )

    result = await search_agent.ainvoke(
        {"messages": [HumanMessage(content=prompt)]},
        context=search_context,
        config={"recursion_limit": 10},
    )
    return result["messages"][-1].content
