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
        prefetch_fn=_hook_prefetch,
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
        prefetch_fn=_overlay_prefetch,
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


def build_skills_catalog() -> str:
    """Return the skills section for the orchestrator system prompt."""
    lines = ["## Available Skills\n"]
    for skill in SKILLS.values():
        lines.append(f"### {skill.name}")
        lines.append(f"**What it does:** {skill.description}")
        lines.append(f"**Use when:** {skill.when_to_use}\n")
    return "\n".join(lines)
