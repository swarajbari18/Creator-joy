from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable, Any

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
            if self.prompt_path.exists():
                self._prompt_cache = self.prompt_path.read_text()
            else:
                self._prompt_cache = f"Stub prompt for {self.name}"
        return self._prompt_cache


async def _hook_prefetch(project_id: str, video_ids: list[str], situational_prompt: str) -> str:
    """Pre-fetch first 30 seconds for HookDiagnosis."""
    from creator_joy.rag.models import StructuralFilters
    from creator_joy.chat.tools import _format_search_result, get_rag_service
    rag = get_rag_service()
    result = rag.search(
        project_id=project_id,
        video_ids=video_ids,
        filters=StructuralFilters(timecode_start_max_seconds=30.0),
        operation="FETCH",
        top_k=20,
    )
    return _format_search_result(result, "FETCH")


async def _overlay_prefetch(project_id: str, video_ids: list[str], situational_prompt: str) -> str:
    """Pre-fetch all segments for OverlayAudit."""
    from creator_joy.rag.models import StructuralFilters
    from creator_joy.chat.tools import _format_search_result, get_rag_service
    rag = get_rag_service()
    result = rag.search(
        project_id=project_id,
        video_ids=video_ids,
        operation="FETCH",
        top_k=300,   # fetch all segments
    )
    return _format_search_result(result, "FETCH")


SKILLS: dict[str, Skill] = {
    "search_skill": Skill(
        name="search_skill",
        description="Directly queries the video segment database. Can count segments, get field distributions, fetch segments by timecode or field filters, compute total duration, and retrieve full segment data. The fastest path to raw data when you know what you need.",
        when_to_use="Useful for direct data questions: counts, distributions, timecode lookups, fetching segment content, or any question you can answer with data retrieval alone.",
        prompt_path=SKILLS_DIR / "search_skill" / "skill.md",
        category="search",
    ),
    "HookDiagnosis": Skill(
        name="HookDiagnosis",
        description="Retrieves and structures all observable data from the first 30 seconds of a video — opening line, shot composition, text overlays, music state, camera work, and cut patterns. Useful whenever you need to understand how a video begins or what the first impression looks like.",
        when_to_use="Useful for understanding openings, hooks, first impressions, intros, or anything in the first 30 seconds.",
        prompt_path=SKILLS_DIR / "HookDiagnosis" / "skill.md",
        category="pre_injected",
        prefetch_fn=_hook_prefetch,
    ),
    "TwoVideoComparison": Skill(
        name="TwoVideoComparison",
        description="Retrieves the same data dimensions from two videos and presents them side by side. Ensures symmetrical comparison — both sides get the same treatment. Good for understanding differences and similarities between any two videos.",
        when_to_use="Useful when comparing two specific videos on any dimension — production choices, content structure, editing style, or overall approach.",
        prompt_path=SKILLS_DIR / "TwoVideoComparison" / "skill.md",
        category="dynamic",
    ),
    "RetentionDiagnosis": Skill(
        name="RetentionDiagnosis",
        description="Retrieves what was happening in a video at and around a specific timecode — transcript, shot type, music state, topic transitions, editing events. Helps understand the context of any particular moment in the video.",
        when_to_use="Useful for investigating what happened at a specific moment, diagnosing drop-off points, or understanding context around a timecode.",
        prompt_path=SKILLS_DIR / "RetentionDiagnosis" / "skill.md",
        category="dynamic",
    ),
    "ScriptAnalysis": Skill(
        name="ScriptAnalysis",
        description="Retrieves verbatim transcript text from video segments. Returns exact words spoken with timecodes, preserving filler words, pauses, and inaudible markers. The go-to skill when exact spoken words matter.",
        when_to_use="Useful for getting exact quotes, verbatim transcript, or what was said at any point in the video.",
        prompt_path=SKILLS_DIR / "ScriptAnalysis" / "skill.md",
        category="dynamic",
    ),
    "SingleVideoAnalysis": Skill(
        name="SingleVideoAnalysis",
        description="A versatile analysis skill for any question about a single video. Can retrieve and synthesize data about content themes, visual style, production patterns, segment breakdowns, and more. Works well for open-ended questions, overviews, and summaries of a single video.",
        when_to_use="Useful as a general-purpose skill for any single-video question — summaries, overviews, content analysis, style assessment, or anything that does not fit a more specific skill.",
        prompt_path=SKILLS_DIR / "SingleVideoAnalysis" / "skill.md",
        category="dynamic",
    ),
    "ProductionAudit": Skill(
        name="ProductionAudit",
        description="Samples segments across a video's timeline to assess production quality — lighting setup, audio quality, camera work, background, color grading, and microphone type. Provides a representative picture of the video's production characteristics.",
        when_to_use="Useful for understanding production quality, lighting, audio setup, camera work, background, or overall visual and audio polish.",
        prompt_path=SKILLS_DIR / "ProductionAudit" / "skill.md",
        category="dynamic",
    ),
    "EditingAnalysis": Skill(
        name="EditingAnalysis",
        description="Computes editing statistics — cuts per minute, cut type distribution, shot type variation, B-roll usage, and average segment duration. Gives a quantitative picture of a video's editing rhythm and pace.",
        when_to_use="Useful for understanding pacing, editing style, cut frequency, transitions, B-roll usage, or shot variety.",
        prompt_path=SKILLS_DIR / "EditingAnalysis" / "skill.md",
        category="dynamic",
    ),
    "CompetitorIntelligence": Skill(
        name="CompetitorIntelligence",
        description="Looks across multiple competitor videos to identify recurring patterns — what they consistently do in production, content, and style. Focuses on patterns, not one-off observations.",
        when_to_use="Useful for understanding a competitor's recurring strategy, signature style, or consistent production choices across their videos.",
        prompt_path=SKILLS_DIR / "CompetitorIntelligence" / "skill.md",
        category="dynamic",
    ),
    "SeriesAnalysis": Skill(
        name="SeriesAnalysis",
        description="Finds patterns across multiple of the creator's own videos — what is consistent in their catalog, what has changed over time, and what production choices correlate with engagement differences.",
        when_to_use="Useful for understanding trends across the creator's own catalog, evolution over time, or finding what their best videos have in common.",
        prompt_path=SKILLS_DIR / "SeriesAnalysis" / "skill.md",
        category="dynamic",
    ),
    "OverlayAudit": Skill(
        name="OverlayAudit",
        description="Returns a complete chronological inventory of every text overlay, graphic, animation, and lower-third in a video. Exhaustive — covers the entire video, not just a sample.",
        when_to_use="Useful for understanding what text, graphics, or visual elements appear on screen throughout a video.",
        prompt_path=SKILLS_DIR / "OverlayAudit" / "skill.md",
        category="pre_injected",
        prefetch_fn=_overlay_prefetch,
    ),
    "AudioAnalysis": Skill(
        name="AudioAnalysis",
        description="Analyzes the audio landscape of a video — music presence and genre, tempo changes, sound effects, ambient audio, and audio quality throughout. Builds a timeline of all audio events.",
        when_to_use="Useful for understanding music choices, sound design, audio quality, or the overall audio atmosphere of a video.",
        prompt_path=SKILLS_DIR / "AudioAnalysis" / "skill.md",
        category="dynamic",
    ),
    "EngagementCorrelation": Skill(
        name="EngagementCorrelation",
        description="Cross-references production data from video segments with engagement metrics to surface observable correlations. Reports patterns without asserting causation — helps the creator form hypotheses.",
        when_to_use="Useful for exploring whether production choices correlate with engagement differences across videos.",
        prompt_path=SKILLS_DIR / "EngagementCorrelation" / "skill.md",
        category="dynamic",
    ),
    "ShortFormOptimization": Skill(
        name="ShortFormOptimization",
        description="Specialized analysis for short-form content under 60 seconds. Uses a 3-second hook window (not 30s), evaluates completion-rate signals, and assesses platform-specific audio relevance for Shorts, Reels, and TikTok.",
        when_to_use="Useful for analyzing content under 60 seconds — Shorts, Reels, TikToks, or any vertical short-form video.",
        prompt_path=SKILLS_DIR / "ShortFormOptimization" / "skill.md",
        category="dynamic",
    ),
}


def build_skills_catalog() -> str:
    """Return the skills section for the orchestrator system prompt."""
    lines = ["## Available Skills\n"]
    for skill in SKILLS.values():
        lines.append(f"### {skill.name}")
        lines.append(f"{skill.description}")
        lines.append(f"*{skill.when_to_use}*\n")
    return "\n".join(lines)

