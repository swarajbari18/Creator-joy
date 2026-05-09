# CreatorJoy Chatbot Architecture: Simulation, Gap Analysis, and Research Findings

**Written:** 2026-05-09  
**Purpose:** Pre-build validation of the proposed Main Orchestrator + Sub-Agent architecture. This document is adversarial — it actively tries to find where the design fails.  
**Scope:** 10+ chat simulations, complete gap analysis, targeted web research per gap, and final recommendations.

---

## Table of Contents

1. [Architecture Recap](#1-architecture-recap)
2. [Phase 1: Chat Session Simulations (10+)](#2-phase-1-chat-session-simulations)
3. [Phase 2: Gap Analysis and Failure Modes](#3-phase-2-gap-analysis-and-failure-modes)
4. [Phase 3: Web Research Findings Per Gap](#4-phase-3-web-research-findings-per-gap)
5. [Final Recommendations](#5-final-recommendations)

---

## 1. Architecture Recap

For reference throughout simulations, the proposed architecture:

```
Main Orchestrator Agent (Gemini)
├── System prompt: skill knowledge + engagement metrics + conversation history (SQLite)
├── EXACTLY ONE tool: use_sub_agent_with_skill(skill_name, situational_prompt)
└── Sub-agents spawned dynamically:
    ├── System prompt = skill.md file content
    ├── Human message = situational_prompt from main agent
    ├── Tools: search_segments (Qdrant, with project_id/video_ids injected at runtime)
    └── Returns findings → main agent synthesizes

Streaming: tool call events emit "Using SearchSkill..." to user
Memory: full conversation history in SQLite → injected into main agent context
```

**Concrete data available (from current build):**  
- Per-segment: segment_id, timecode_start/end, shot_type, camera_angle, camera_movement, transcript, speaker_id, all lighting fields, background, on_screen_text entries, graphics entries, cut_type, music fields, production_observables  
- Video-level (from yt-dlp): views, likes, comments, channel_follower_count, duration, upload_date, platform, title, creator_name  
- Skills designed: SearchSkill + AnalysisSkill (current), plus 10 richer skills in docs/chat_skill.md (HookDiagnosis, TwoVideoComparison, ProductionAudit, EditingAnalysis, ScriptAnalysis, OverlayAudit, AudioAnalysis, SeriesAnalysis, CompetitorIntelligence, EngagementCorrelation)

The simulations below use the **proposed architecture as described** (single tool, dynamically spawned sub-agents), not the richer 10-skill architecture from chat_skill.md. Gaps in that mismatch are explicitly noted.

---

## 2. Phase 1: Chat Session Simulations

Each simulation follows this trace format:
- **User input**
- **Main agent reasoning** (internal)
- **Tool call decision**
- **Situational prompt written to sub-agent**
- **Sub-agent execution** (tool calls + results)
- **Sub-agent return**
- **Main agent synthesis**
- **What user sees**
- **Critical observations**

---

### Simulation 1 — Simple: "What's the engagement rate on my two videos?"

**User:** "What's the engagement rate on my two videos?"

**Main agent reasoning:**  
Engagement rate is stored at the video level in the system prompt context (engagement metrics for loaded videos are injected into the main agent's system prompt). The agent checks its context: Video A (vid_A): views=12,400, likes=310, comments=89, channel_followers=8,200. Video B (vid_B): views=47,300, likes=2,180, comments=412, channel_followers=8,200. ER = (likes + comments) / views. Can answer without calling any sub-agent.

**Tool call decision:** NONE — answers from its own context.

**What user sees:**
```
Video A:
  ER_views = (310 + 89) / 12,400 = 3.2%
  Like rate = 310 / 12,400 = 2.5%

Video B:
  ER_views = (2,180 + 412) / 47,300 = 5.5%
  Like rate = 2,180 / 47,300 = 4.6%

Video B is performing significantly better — 72% higher engagement rate.
Follower base is the same (8,200), so the difference is in the content, not the audience.
```

**Critical observations:**  
This works correctly. Engagement metrics in the main agent's system prompt means no sub-agent call needed. This is the right design for numerical lookups.

**FAILURE MODE identified:** The main agent is told it "knows engagement metrics for loaded videos" but the architecture does not specify *exactly* what format those metrics come in or whether computed ER fields are pre-computed vs. computed by the LLM on the fly. If the LLM has to compute ER from raw counts, it can make arithmetic errors. Gemini Flash has been documented making simple arithmetic mistakes on multi-step division. **The ER computation should be pre-computed and stored, not derived by the LLM at response time.**

---

### Simulation 2 — Simple: "How many jump cuts does Video A have?"

**User:** "How many jump cuts does Video A have?"

**Main agent reasoning:**  
This requires counting `cut_type = "jump-cut"` across all segments in Video A. This is data in Qdrant, not available in context. Must call a sub-agent.

**Tool call decision:** `use_sub_agent_with_skill("SearchSkill", situational_prompt)`

**Situational prompt from main to sub-agent:**
```
USER GOAL: Creator wants to know how many jump cuts appear in Video A.

WHAT IS KNOWN SO FAR: Nothing has been retrieved yet. This is the first query.

WHAT TO DO NOW: Count the number of segments in Video A that have cut_type = "jump-cut".
Video A's video_id is "vid_A_uuid". Project ID is "proj_uuid".

WHY THIS SUB-AGENT IS BEING CALLED: We need an exact count from Qdrant structural data.

Return: a single integer count.
```

**Sub-agent execution:**  
SearchSkill reads its skill.md. Decides: Mode 1 structural, operation=COUNT, filters: cut_type="jump-cut", video_ids=["vid_A_uuid"].

Tool call:
```python
search_segments(
    project_id="proj_uuid",
    video_ids=["vid_A_uuid"],
    filters=StructuralFilters(cut_type="jump-cut"),
    operation="COUNT"
)
```

Result: `{ total_count: 23, segments: [], mode: "structural", operation: "COUNT" }`

**Sub-agent return:** "Video A has 23 segments with cut_type = jump-cut."

**Main agent synthesis:**  
Takes the count. Optionally enriches: "If the video is 8 minutes long, that's ~2.9 jump cuts per minute." Duration is in its context from engagement metrics. Outputs the answer.

**What user sees:**
```
Video A has 23 jump cuts.
At 8:12 runtime, that's approximately 2.8 jump cuts per minute — a fast-paced editing style.
```

**Critical observations:**  
Works correctly. The situational prompt successfully tells the sub-agent exactly what to do without over-constraining the output format.

**FAILURE MODE identified:** The main agent's system prompt must include the video_id UUID mappings so it can tell the sub-agent "vid_A_uuid = fdb0d91b..." without guessing. If the system prompt only says "Video A (by CreatorName, uploaded 2025-03-14)" and doesn't include the UUID, the main agent **cannot** construct the situational prompt correctly. This UUID-to-human-name mapping is a data injection problem that isn't explicitly addressed in the architecture spec.

---

### Simulation 3 — Medium: "What's different about my hook compared to the competitor's?"

**User:** "What's different about my hook compared to the competitor's?"

**Main agent reasoning:**  
"My hook" = Video A first ~30 seconds. "Competitor's" = Video B first ~30 seconds. Needs to retrieve hook segments from both videos and compare. This will require at least two sub-agent calls (or one call covering both), and then synthesis. Also needs: transcript, shot type, on-screen text, cut events, camera, music for each hook. This is a HookDiagnosis + TwoVideoComparison scenario.

**Decision:** Call SearchSkill twice — once per video — to get hook segments from each.

**First tool call:**  
```
Situational prompt for Video A hook:
USER GOAL: Compare hooks of two videos. Currently fetching Video A's hook.
WHAT TO FIND: All segments from Video A (vid_A_uuid) with timecode_start < 30 seconds.
Return full segment payloads including: transcript, shot_type, on_screen_text, cut_type, music_present, camera_angle.
Project ID: proj_uuid.
```

**Sub-agent execution (Video A hook):**  
Mode 1 structural, FETCH, filters: timecode_start_max_seconds=30.0, video_ids=["vid_A_uuid"].  
Returns 4 segments (0:00–0:08, 0:08–0:15, 0:15–0:23, 0:23–0:31).

**Second tool call (Video B hook):**  
Identical prompt targeting vid_B_uuid.  
Returns 3 segments (0:00–0:11, 0:11–0:22, 0:22–0:31).

**Main agent synthesis:**  
Compares field by field:
- Shot type: A opens MCU. B opens ECU (extreme close-up, more aggressive).
- First spoken word at: A at 0:00 ("Hey guys..."). B at 0:03 (3-second silent B-roll intro).
- On-screen text: A has no text in first 30s. B has "THIS CHANGED EVERYTHING" at 0:02.
- Cut events: A has 2 cuts in 30s. B has 6 cuts (jump-cut heavy).
- Music: A has no music. B has upbeat-pop from 0:00.

**What user sees:**
```
Key hook differences (first 30 seconds):

SHOT: Your video opens on MCU (medium close-up). Competitor opens ECU — much more intimate, 
fills the frame with face immediately.

TEXT OVERLAY: You have no on-screen text. Competitor shows "THIS CHANGED EVERYTHING" 
at 0:02 — a hook promise before speaking.

PACING: You make 2 cuts in 30s (slow, deliberate). Competitor makes 6 jump cuts — 
faster, more kinetic energy.

MUSIC: You have no background music in your hook. Competitor has upbeat-pop from frame 1 — 
sets emotional tone before the creator speaks.

OPENING LINE: You open speaking immediately ("Hey guys..."). Competitor has 3 seconds of 
B-roll before speaking — visual hook before verbal hook.
```

**Critical observations:**  
This works but reveals a latency problem. Two sequential sub-agent calls means two full LangChain agent spin-ups, two Qdrant calls, two LLM inference passes. For a "medium" query, that's potentially 6-10 seconds of wall time. The user sees "Using SearchSkill..." twice with a gap between them.

**FAILURE MODE identified #1:** The main agent may not know when it has "enough" data. It might call sub-agents 3-4 times for a comparison that could be done in 2. No mechanism prevents over-calling.

**FAILURE MODE identified #2:** The comparison synthesis happens in the main agent, but the main agent received raw segment data, not pre-analyzed data. If Video A returns 4 segments and Video B returns 3, and each has a full payload, the main agent's context window is being used to hold all of that raw data before synthesis. For a long video, this could be significant.

---

### Simulation 4 — Medium: "Why does Video B feel more professional than Video A?"

**User:** "Why does Video B feel more professional than Video A?"

**Main agent reasoning:**  
"Professional" maps to: audio quality (clean-studio vs heavy-reverb), lighting (soft, catch_light_in_eyes=true vs hard/none), color grade (vibrant/neutral vs desaturated), microphone type (lav/shotgun vs built-in), background (studio vs messy home-office). Needs production fields from both. This is a ProductionAudit on both videos + comparison.

**Decision:** Call SearchSkill twice — once per video — fetching production-heavy fields.

**First tool call (Video A production):**  
Situational prompt specifies: fetch representative segments (beginning, middle, end — roughly 3 segments) for Video A, looking for: audio_quality, key_light_direction, light_quality, catch_light_in_eyes, color_grade_feel, microphone_type, background_type, color_temperature_feel.

**Sub-agent execution:**  
Mode 1 structural, FETCH with timecode constraints to sample from 3 points in the video. Returns 3 segments.

**FAILURE POINT:** The SearchSkill doesn't have a "sample from beginning/middle/end" operation. The skill.md describes MODE 1 structural which can filter by timecode range, but "representative sampling" requires multiple calls or a non-existent SAMPLE operation. The sub-agent would have to call search_segments three times (0–30s, middle range, last 30s) or return everything and let the main agent sample. Neither is explicitly supported.

**What actually happens:** Sub-agent likely calls FETCH with no timecode filter, returns all segments (could be 50+). Main agent receives a giant context dump, must self-select which segments to analyze.

**Main agent synthesis (best case):**  
Picks segments 1, 25, 50. Compares:
- Video A: audio_quality="light-room-echo", key_light="above" (ceiling light), catch_light_in_eyes=false, microphone="built-in", color_grade="desaturated"
- Video B: audio_quality="clean-studio", key_light="left", light_quality="soft", catch_light_in_eyes=true, microphone="lav", color_grade="warm"

**What user sees (good path):**
```
Concrete reasons Video B appears more professional:

AUDIO: Video B has clean-studio audio (likely lav mic). Video A shows light room echo 
and appears to use a built-in microphone — the biggest production quality signal.

LIGHTING: Video B uses soft key light from the left, with catch light visible in eyes 
(professional lighting rig). Video A uses ceiling/above light (overhead, unflattering, 
no catch light — classic amateur setup).

COLOR: Video B has warm color grade. Video A is desaturated — looks flatter/cheaper.

BACKGROUND: [depends on what segments returned]
```

**Critical observations:**  
The answer is correct if the main agent picks representative segments. But the main agent is working with up to 50 raw segment payloads in its context. This is context window waste and a quality risk — the main agent has to do the "sampling" work that should ideally be done closer to the data.

**FAILURE MODE identified:** No "representative sample" operation in SearchSkill. Workarounds (return everything, client-side sample) are inefficient and unreliable.

---

### Simulation 5 — Complex: "Why is my competitor's video getting more views than mine?"

**User:** "Why is my competitor's video getting more views than mine?"

**Main agent reasoning:**  
Views: Video A has 12,400 views. Video B (competitor) has 47,300 views. 3.8x more. Why? This requires:
1. Hook comparison (first impressions)
2. Editing pace comparison (cut rate, energy)
3. Production quality comparison
4. Thumbnail/title (not available in transcription data — thumbnails aren't ingested)
5. Upload timing (upload_date is available in engagement metrics)
6. Observable content differences

This is the "money query." The main agent must retrieve production, editing, and script data from both videos and synthesize. Minimum 4-6 sub-agent calls.

**Actual execution:**

Call 1: Hook segments from both videos (timecode < 30s).  
Call 2: Editing data from both (cut distribution).  
Call 3: Production data from both (audio, lighting).  
Call 4 (maybe): Script/content from both to see if topic framing differs.

**FAILURE POINT 1 — Over-claiming causation:**  
The main agent is asked "WHY is this getting more views?" but views are driven by: thumbnail, title, SEO, posting time, algorithm promotion, community size, virality, and *then* content quality. The RAG system has zero data on thumbnail, title SEO quality, algorithm context, or external traffic sources. The main agent, if not carefully constrained, will produce a confident-sounding answer about production differences "causing" more views — which is correlation at best, causation at worst.

**FAILURE POINT 2 — Query scope explosion:**  
The main agent might call SearchSkill 5-6 times sequentially, each call taking 2-3 seconds. Total latency: 12-18 seconds. The user sees "Using SearchSkill..." six times. This is not a good user experience for a single question.

**FAILURE POINT 3 — Synthesis quality:**  
After 5-6 sub-agent calls, the main agent has received a large amount of raw segment data. It must synthesize this into a coherent narrative while the conversation history is also in its context. Context bloat is real here.

**What user sees (best case):**
```
Observable differences that likely contribute to the performance gap:

VIEWS CONTEXT: Your video has 12,400 views vs competitor's 47,300 — a 3.8x difference. 
Note: views are influenced by thumbnail, title, and algorithm — this analysis covers 
observable video production differences only.

HOOK (first 30s): [comparison as per Simulation 3]

EDITING PACE: Competitor uses 6 jump cuts in 30s (2.8/min across full video). 
Your video uses 2 cuts in 30s (1.1/min) — significantly slower pacing.

AUDIO: Competitor has clean-studio audio throughout. Your video has light room echo.

PRODUCTION TIER: These differences suggest competitor invested more in production setup. 
However, we cannot confirm these factors *caused* the view difference — algorithm, 
thumbnail quality, and posting timing are not available in this analysis.

RECOMMENDATION: Ingesting more videos from each creator would help identify whether 
these differences are consistent patterns or one-off choices.
```

**Critical observations:**  
The good path produces a useful answer. The bad path (main agent over-claims causation) is the failure mode that would destroy user trust. This cannot be left to LLM judgment alone — it must be enforced by system prompt constraint.

---

### Simulation 6 — Complex: "Walk me through everything happening in the first 30 seconds of Video A"

**User:** "Walk me through everything happening in the first 30 seconds of Video A"

**Main agent reasoning:**  
This is a chronological narration of all observable data in the first 30 seconds. Needs to retrieve all segments with timecode_start < 30 seconds and return them in order. One sub-agent call is sufficient.

**Tool call:**  
Situational prompt: "Retrieve ALL segments from Video A (vid_A_uuid) where timecode_start < 30 seconds. Return them in segment_id order. Include: timecode_start, timecode_end, transcript, shot_type, camera_angle, on_screen_text entries (with exact text), cut_type, music_present, observable_summary."

**Sub-agent execution:**  
Mode 1 structural, FETCH, timecode_start_max_seconds=30.0, video_ids=["vid_A_uuid"]. Returns 4 segments ordered by segment_id.

**Sub-agent return:**  
```json
[
  { "segment_id": 1, "timecode_start": "0:00", "timecode_end": "0:08",
    "shot_type": "MCU", "camera_angle": "eye-level",
    "transcript": "Hey everyone, so today I want to talk about something...",
    "on_screen_text": [], "cut_type": null, "music_present": false,
    "observable_summary": "Creator faces camera in MCU, speaking directly to viewer" },
  { "segment_id": 2, "timecode_start": "0:08", "timecode_end": "0:15",
    "shot_type": "B-roll", "camera_angle": "eye-level",
    "transcript": "",
    "on_screen_text": [{"text": "3 YEARS OF RESEARCH", "position": "center"}],
    "cut_type": "hard-cut", "music_present": false,
    "observable_summary": "Cut to B-roll footage, text overlay appears" },
  ...
]
```

**Main agent synthesis:**  
Walks through chronologically, weaving narrative:

**What user sees:**
```
Here's a second-by-second breakdown of your first 30 seconds:

0:00–0:08 (Segment 1): You open on a medium close-up, eye-level, speaking directly to 
camera. No music, no text. Opening line: "Hey everyone, so today I want to talk about 
something..." You establish presence but haven't delivered a hook yet.

0:08–0:15 (Segment 2): Hard cut to B-roll. First text overlay appears at center: 
"3 YEARS OF RESEARCH." No audio from you during this B-roll.

0:15–0:23 (Segment 3): [etc.]

0:23–0:31 (Segment 4): [etc.]
```

**Critical observations:**  
This works well. Single sub-agent call, chronological retrieval, natural synthesis. This is the happy path.

**FAILURE MODE identified:** The segment boundary might split mid-sentence. If a sentence starts at 0:07 and ends at 0:10, segment 1 (0:00–0:08) has "Hey everyone, so today I want to talk about some-" and segment 2 picks up "thing really important..." The verbatim narration will look weird. This is a schema issue (segment boundaries are at observable changes, not sentence boundaries) not a chatbot issue, but the chatbot needs to handle it gracefully rather than presenting the incomplete transcript as a complete sentence.

---

### Simulation 7 — Follow-up: Reference to something 3 messages earlier

**Conversation history:**
```
Turn 1: User: "What shot types does Video A use most?"
Turn 2: Bot: "Video A is predominantly MCU (48% of runtime), followed by B-roll (22%)..."
Turn 3: User: "What about the music?"
Turn 4: Bot: "Video A has lo-fi music in 60% of segments, silence in 40%..."
Turn 5: User: "Does the competitor use the same shot distribution?"
```

**Main agent reasoning:**  
"The competitor" refers to Video B (established context). "Same shot distribution" — needs shot type GROUP_BY for Video B. Has context from turn 2 about Video A shot distribution. One sub-agent call.

**Situational prompt:**
```
USER GOAL: Compare shot type distribution of Video B to what we already found for Video A.

WHAT IS KNOWN FROM EARLIER IN CONVERSATION (turn 2):
Video A shot distribution: MCU=48%, B-roll=22%, CU=18%, WS=12%

WHAT TO DO NOW: Get the shot type distribution (GROUP_BY shot_type) for Video B (vid_B_uuid).
Project ID: proj_uuid. Return the group_by_data showing count per shot_type.

WHY: User wants to compare the two distributions side-by-side.
```

**Sub-agent execution:**  
Mode 1 GROUP_BY, group_by_field="shot_type", video_ids=["vid_B_uuid"]. Returns: {MCU: 31, CU: 12, WS: 8, B-roll: 27, EWS: 2}. Total: 80 segments.

**Main agent synthesis:**  
Normalizes counts to percentages. Compares to Video A data from turn 2 (which is in conversation history).

**What user sees:**
```
Competitor (Video B) shot distribution vs yours (Video A):

Shot Type    | Video A | Video B
-------------|---------|--------
MCU          | 48%     | 39%
B-roll       | 22%     | 34%
CU           | 18%     | 15%
WS           | 12%     | 10%

Biggest difference: Video B uses significantly more B-roll (34% vs your 22%). 
They're cutting away from talking-head more frequently.
```

**Critical observations:**  
This works because the conversation history (injected from SQLite) contains the Video A data from turn 2. The main agent correctly uses prior conversation context to enrich the situational prompt.

**FAILURE MODE identified:** As conversations grow long, the main agent's context window fills with accumulated conversation history + all the raw data returned from previous sub-agent calls. If the user has been chatting for 20 turns, the context includes: 20 user messages, 20 bot responses, and all the raw segment payloads returned along the way. At ~500 tokens per turn (including data), a 20-turn conversation is already ~10,000 tokens of history before any new retrieval happens. At 40 turns, it's potentially ~20,000 tokens. **There is no memory compaction mechanism in the proposed architecture.** This is a time bomb.

---

### Simulation 8 — Ambiguous: "Make my video better"

**User:** "Make my video better"

**Main agent reasoning:**  
Extremely underspecified. "Better" could mean: more views (EngagementCorrelation), better production quality (ProductionAudit), better hook (HookDiagnosis), better editing pace (EditingAnalysis), or all of the above. The proposed architecture has no explicit ambiguity-resolution mechanism. The main agent must decide: clarify or pick a default?

**Option A — Clarify (correct behavior):**  
Main agent says: "I can help with that! Which aspect are you most interested in improving first? Options: hook (first 30 seconds), production quality (lighting, audio, camera), editing pace (cut rate, transitions), or script/content?"

**Option B — Make assumptions and proceed (risky behavior):**  
Main agent decides "make better = compare to competitor and find gaps" and fires off 4 sub-agent calls.

**What the main agent actually does:**  
This depends entirely on the main agent's system prompt. The proposed architecture spec does **not** include explicit ambiguity-resolution instructions. Without them, Gemini will probabilistically either:
- Ask a clarifying question (Option A) — reasonable
- Pick the most common interpretation and proceed (Option B) — risky
- Try to address all dimensions at once with multiple sub-agent calls — latency disaster

**What user most likely sees with current spec:**  
Gemini tends toward being helpful/proactive. It will likely say "Let me analyze several dimensions of your video" and fire 3-4 sub-agent calls. User waits 15-20 seconds for a broad audit they didn't necessarily want.

**Critical observations:**  
**This is a critical gap.** The architecture has no disambiguation layer. The main agent's system prompt must contain explicit instructions for how to handle underspecified queries:
- Ask ONE clarifying question before proceeding
- Do not fire multiple sub-agent calls for ambiguous queries
- Offer a menu, not an assumption

---

### Simulation 9 — Edge Case: User asks about a video that hasn't been ingested

**User:** "Can you analyze my latest video? It's at youtube.com/watch?v=XYZ123"

**Main agent reasoning:**  
The main agent's system prompt contains engagement metrics and video metadata for "loaded videos." XYZ123 is not in that list. How does it respond?

**What the architecture currently handles:**  
The main agent knows about videos whose metadata is in its system prompt. If XYZ123 is not there, the main agent's system prompt simply doesn't mention it. The main agent doesn't have a database lookup tool — it only has `use_sub_agent_with_skill`.

**Option A — Main agent correctly identifies the gap:**  
Main agent: "I don't see youtube.com/watch?v=XYZ123 in your project. To analyze it, you'll need to ingest it first. [Instructions for ingestion]."

**Option B — Main agent tries to call SearchSkill anyway:**  
Situational prompt: "Search for Video XYZ123..." Sub-agent calls Qdrant with a non-existent video_id. Qdrant returns 0 results. Sub-agent returns: "No segments found for this video." Main agent synthesizes: "I couldn't find data for that video" — but doesn't explain *why* (it hasn't been ingested).

**Option C — Main agent hallucinates:**  
Main agent doesn't realize the video isn't ingested. It generates a plausible-sounding analysis based on its training knowledge about YouTube video creation. **This is the catastrophic failure path.**

**What actually happens:**  
Without explicit "check if video is in project before proceeding" logic, the main agent will follow Option B or C. Option B is bad UX (confusing error message). Option C destroys trust permanently.

**Critical observations:**  
The architecture has no mechanism to detect "video not in project." The main agent system prompt must include:
1. Complete list of ingested video IDs with their titles and URLs
2. Explicit instruction: "If the user references a video not in this list, do NOT call any sub-agent. Instead, tell them to ingest it first."

Without this, edge case 9 is a landmine.

---

### Simulation 10 — Multi-step: "First tell me about my hook, then compare it to the competitor, then suggest improvements"

**User:** "First tell me about my hook, then compare it to the competitor, then suggest improvements"

**Main agent reasoning:**  
Three explicit phases:
1. Describe own hook
2. Compare to competitor
3. Suggest improvements

The user has explicitly sequenced these. The main agent must execute them in order, showing progress at each step.

**Execution:**

**Phase 1 — Retrieve own hook:**  
Sub-agent call 1: FETCH segments, Video A, timecode < 30s.  
Main agent synthesizes: "Your hook: You open MCU, speaking immediately, no text overlay, no music, 2 cuts in 30s..."  
Streams partial answer to user.

**Phase 2 — Retrieve competitor hook:**  
Sub-agent call 2: FETCH segments, Video B, timecode < 30s.  
Main agent synthesizes comparison (as in Simulation 3).  
Streams comparison to user.

**Phase 3 — Suggest improvements:**  
Here is where the system hits a critical architectural limit. "Suggest improvements" is not a retrieval task. It's a reasoning task. The main agent doesn't need to call SearchSkill — it should synthesize from the data it already has in context (from phases 1 and 2) and reason about what changes would help.

**Does the main agent call SearchSkill a third time?**  
Without explicit instructions, it might. It might try to call "AnalysisSkill" if that's in scope. Or it might correctly reason from existing context.

**What user sees (good path):**
```
[After Phase 1 — streaming]
Your hook analysis:
Your opening 30 seconds use an MCU, no music, no text overlay, and 2 cuts...

[After Phase 2 — streaming]
Competitor comparison:
Their hook is more aggressive: ECU, upbeat music from frame 0, text overlay 
("THIS CHANGED EVERYTHING") at 2 seconds, 6 jump cuts...

[After Phase 3 — reasoning from context]
Suggested improvements based on the gap:
1. Add an on-screen text hook in your first 3 seconds — a specific promise 
   or claim, not a description of what you're doing.
2. Consider 1-3 seconds of B-roll before speaking — it creates visual context.
3. Your pacing (2 cuts in 30s) is slow vs competitor (6 cuts). Try tightening 
   the hook segment with more frequent cuts.
4. Background music from frame 0 sets emotional tone. Consider lo-fi or upbeat 
   track starting at the same moment you appear.
```

**Critical observations:**

**FAILURE MODE 1 — Phase ordering requires the main agent to maintain a multi-step plan across its own responses.** The proposed architecture doesn't have explicit plan tracking. If the user's message contains "first...then...then..." the main agent must internally track: "I've done step 1, now doing step 2, then step 3." There's no explicit plan state. LLMs can lose track of multi-step plans mid-execution, especially if the intermediate responses get long.

**FAILURE MODE 2 — "Suggest improvements" is an analysis/reasoning task, not a retrieval task.** The architecture currently has SearchSkill and (tentatively) AnalysisSkill, but the AnalysisSkill's role and toolset aren't defined. The main agent may try to call SearchSkill for improvement suggestions, which would return segment data — not improvement recommendations.

**FAILURE MODE 3 — Latency.** Two sequential sub-agent calls (each 2-4 seconds) + synthesis (1-2 seconds) + streaming. Total: 8-12 seconds for a single user message. For a three-part query explicitly sequenced by the user, this might be acceptable — but it must be communicated to the user via good streaming UI.

---

### Simulation 11 — Bonus: "What is my most-used shot type?"

**User:** "What is my most-used shot type?"

**Main agent reasoning:**  
GROUP_BY shot_type for all videos in the project (or just "my" videos, i.e., not the competitor's). Needs sub-agent.

**Situational prompt:**  
"Run GROUP_BY on shot_type across all of the creator's videos (not the competitor's). Creator's video IDs: [vid_A_uuid]. Project ID: proj_uuid. Return the group_by_data showing count per shot_type."

**Sub-agent execution:**  
Mode 1, GROUP_BY, group_by_field="shot_type". Returns: {MCU: 38, B-roll: 17, CU: 14, WS: 9}.

**Main agent synthesis:**  
MCU = 38 out of 78 total segments = 49%. Returns answer.

**FAILURE MODE identified:** The situational prompt says "creator's videos (not the competitor's)." But the main agent determines which video_ids to pass based on its system prompt context — specifically, it needs to know which video_ids belong to the creator vs. the competitor. If the system prompt doesn't clearly label which videos are "yours" vs "competitor's," the main agent might include all video_ids in the GROUP_BY and conflate the two creators' data.

**This is a metadata classification problem.** The system prompt must include: "Creator's own videos: [list of IDs]" and "Competitor videos: [list of IDs]" as explicit labeled categories. Otherwise the main agent guesses from video titles/creator names, which is fragile.

---

### Simulation 12 — Bonus: "How long is my competitor's video?"

**User:** "How long is my competitor's video?"

**Main agent reasoning:**  
Duration is a video-level field (in seconds) from yt-dlp metadata. If it's in the main agent's system prompt as part of "engagement metrics for loaded videos," this doesn't need a sub-agent call.

**What actually happens:**  
If duration IS in the main agent system prompt: answers immediately. Correct.  
If duration is NOT in the main agent system prompt (only view/like/comment counts): the main agent will either call SearchSkill (which can SUM_duration across all segments to reconstruct the total, but that's indirect) or say "I don't know."

**FAILURE MODE:** The "engagement metrics" injected into the main agent system prompt are not fully defined in the architecture spec. What fields exactly? Views, likes, comments? Does duration get included? If not, simple questions like "how long is this video?" require a sub-agent call just to do SUM_duration on all segments — wasteful.

**The main agent system prompt template must be fully specified.** The architecture spec currently says "engagement metrics for loaded videos" without listing the exact fields. This ambiguity will cause inconsistent behavior.

---

## 3. Phase 2: Gap Analysis and Failure Modes

Based on the 12 simulations above, here is a complete and honest enumeration of every identified failure mode, organized by severity.

---

### Gap 1 — The Single-Tool Bottleneck (CRITICAL)

**What it is:** The main agent has exactly one tool: `use_sub_agent_with_skill`. Any query requiring multiple retrieval passes must call this tool sequentially. There is no mechanism for parallel sub-agent execution.

**Where it fails:**
- Simulation 3: Hook comparison requires 2 sequential sub-agent calls (one per video). Each call is a full LangChain agent spin-up + Qdrant query + LLM inference pass. Wall time: 6-10 seconds for what is a simple "fetch two sets of segments."
- Simulation 5: "Why is competitor getting more views?" triggers 4-6 sequential sub-agent calls. Wall time: 15-25 seconds.
- Simulation 10: Three-phase query runs 2 sub-agent calls before even reaching synthesis.

**Why it's critical:** At 3+ sequential sub-agent calls, user latency is unacceptable. Users typing into a chat interface expect responses in under 5 seconds. At 15-25 seconds, users will assume the system crashed or will context-switch away. Even with good streaming UI ("Using SearchSkill... Analyzing hook..."), the total latency is painful.

**The deeper problem:** The single-tool design was chosen for simplicity. But it forces serialization of what could be parallel work. A hook comparison needs Video A's first 30 seconds AND Video B's first 30 seconds — these two Qdrant queries are completely independent and could run simultaneously. The single-tool architecture makes that impossible without adding parallelism at the LangChain orchestration layer.

**Compounding factor:** Each sub-agent call itself has internal latency:
- LangChain agent initialization: ~100-200ms
- Gemini LLM call to interpret situational prompt and decide tool args: ~500ms-1.5s
- Qdrant query: ~20-200ms depending on operation and result size
- Optional reranking (if semantic): ~200-500ms
- LLM call to format results: ~500ms-1s
- Total per sub-agent call: ~1.5-4 seconds

For 4 sequential calls: 6-16 seconds. Not acceptable for a chat product.

---

### Gap 2 — Ambiguity Has No First-Class Handling (CRITICAL)

**What it is:** The architecture has no explicit disambiguation layer. When a query is underspecified ("make my video better," "what should I work on?"), the main agent receives no instructions on how to handle it.

**Where it fails:**
- Simulation 8: "Make my video better" — main agent will either ask a clarifying question (good) or fire multiple sub-agent calls (bad) depending on how the system prompt is written. The architecture spec doesn't mandate which behavior.

**Why it's critical:** Ambiguous queries are extremely common in creator chat. Creators aren't power users of analytics — they're asking open-ended questions. If the system responds to every vague question with a 15-second multi-sub-agent blast, users will distrust the system and stop using it.

**The expected LLM behavior:** Gemini Flash (the proposed main agent model, per cost constraints) is optimized for helpfulness, which means it biases toward doing *something* rather than asking a clarifying question. This is the wrong instinct for this product.

**What's missing:** A mandatory disambiguation step before any sub-agent call, triggered when query specificity is below a threshold. The system prompt must contain: "If the user's query doesn't specify a video, a dimension (production/editing/content), or a goal, ask exactly ONE clarifying question before calling any sub-agent."

---

### Gap 3 — No "Video Not In Project" Detection (CRITICAL)

**What it is:** The system has no mechanism to detect when a user references a video that hasn't been ingested, separate from a video that exists but returns no results.

**Where it fails:**
- Simulation 9: User asks about an un-ingested YouTube URL. The main agent either calls SearchSkill with a bad video_id (returns 0 results, confusing error), or hallucinates an analysis (catastrophic).

**Why it's critical:** Hallucinating video analysis would be the single worst thing this system could do. If a creator makes decisions based on a hallucinated "analysis" of their competitor's video, the product has done active harm.

**The deeper problem:** The Qdrant collection returning 0 results for an unknown video_id is *indistinguishable* from a video that exists but has only silence/no observable events. Both return empty search results. The main agent has no way to differentiate "video not ingested" from "video has nothing to show."

**What's missing:** 
1. The main agent system prompt must include a complete, explicit list of all ingested video IDs (with titles, URLs, creator names) labeled as "Videos available for analysis."
2. An explicit instruction: "Before calling any sub-agent, verify the referenced video is in the above list. If it is not, stop and tell the user to ingest it first."
3. The ingestion system must have an API that returns the current list of ingested videos for a project, so the main agent context can be kept current.

---

### Gap 4 — Conversation Memory Has No Compaction (HIGH)

**What it is:** The proposed architecture stores full conversation history in SQLite and injects it entirely into the main agent's context for every new turn. There is no summarization, truncation, or compaction mechanism.

**Where it fails:**
- Simulation 7: At 40+ conversation turns, the main agent context window contains: full system prompt (skills + metrics + video metadata) + 40 user messages + 40 bot responses (which may contain raw segment data from earlier retrievals). This could be 30,000-50,000 tokens before any new retrieval.

**The math:**
- Main agent system prompt: ~2,000-3,000 tokens (skills, metrics, video metadata)
- Per turn with data: ~500-2,000 tokens (depending on how much sub-agent data the response includes)
- 20 turns: ~12,000-42,000 tokens of history
- 40 turns: ~22,000-82,000 tokens of history
- Gemini Flash context window: 1,000,000 tokens (technically fine)
- Cost: Gemini charges per input token. At 50,000 tokens of history on every turn, a 40-turn conversation costs significantly more per turn than a fresh conversation.
- Latency: Longer input context → longer prefill time → slower TTFT (time to first token).

**The secondary failure:** The conversation history from SQLite includes raw sub-agent outputs (segment payloads, group_by results). These are verbose and contain redundant fields. After the user moves on, retaining the raw Qdrant output from 10 turns ago provides minimal value and wastes context space.

**What's missing:** A compaction strategy. Options:
1. After N turns, summarize older conversation turns and replace them with a compressed summary.
2. Only retain the final synthesized response (not the raw sub-agent output) in conversation history.
3. Use a sliding window: keep only the last K turns of full detail, summarize older turns.

---

### Gap 5 — The Situational Prompt Is Underspecified (HIGH)

**What it is:** The situational prompt format (main → sub-agent) is described conceptually but not formally specified. The main agent writes this free-form based on its understanding of the task.

**Where it fails:**
- Simulation 4: The situational prompt for ProductionAudit needs to request "representative samples from beginning/middle/end" — but this cannot be expressed as a single search_segments call, and the situational prompt has no explicit way to say "make 3 separate calls, one for each section."
- Simulation 11: The situational prompt must correctly filter to "creator's own videos only" — requiring the main agent to embed video_id lists correctly based on creator vs. competitor classification.

**The deeper problem:** The situational prompt is the only channel of communication between the main agent and the sub-agent. If it's incomplete, wrong, or ambiguous, the sub-agent operates on bad instructions. There is no feedback mechanism — the sub-agent cannot ask the main agent for clarification. It just executes and returns.

**Specific failure patterns:**
1. **Under-specification:** Main agent writes "find info about the hook" without specifying timecode range. Sub-agent fetches all segments.
2. **Over-specification:** Main agent writes "use mode 1 structural search with timecode filter" — it's prescribing search mode, which is the SearchSkill's job. Leads to mode confusion.
3. **Missing context:** Main agent forgets to include relevant prior findings in the situational prompt. Sub-agent retrieves redundant data.
4. **Wrong video_id:** Main agent confuses video A and B UUIDs when writing the situational prompt. Sub-agent searches the wrong video.

**What's missing:** A formal situational prompt template, enforced by the main agent system prompt:
```
Required fields:
- user_goal: [what the user is ultimately trying to understand]
- context_from_conversation: [relevant findings from earlier turns]
- task_for_this_call: [exactly what to retrieve, with specific field names and filters]
- video_ids_in_scope: [explicit UUID list]
- why_this_call_is_needed: [what decision the main agent will make with this data]
```

---

### Gap 6 — No "Representative Sampling" Operation (MEDIUM)

**What it is:** The SearchSkill's four operations (FETCH, COUNT, SUM_duration, GROUP_BY) do not include a sampling operation for getting representative segments distributed across a video's timeline.

**Where it fails:**
- Simulation 4: ProductionAudit needs to assess consistency of lighting/audio/color across the video. Sampling 3 segments (beginning, middle, end) is the right approach. Currently impossible with one search_segments call.

**The workaround and its costs:**
- Option 1: FETCH all segments → main agent samples. Problem: for a 20-minute video with 200 segments, the FETCH dumps 200 segment payloads into the sub-agent's context, which then passes them to the main agent.
- Option 2: Make 3 separate search_segments calls with different timecode windows. Problem: requires 3 tool calls, 3× latency.

**What's missing:** A SAMPLE operation or a FETCH with `stride` parameter: return every Nth segment to provide a representative distribution across the video's timeline.

---

### Gap 7 — Synthesis Happens in the Most Expensive Context (MEDIUM)

**What it is:** The main agent (Gemini) does all final synthesis. For complex queries, the main agent receives raw Qdrant segment data from multiple sub-agent calls and must synthesize the answer. This raw data is in the main agent's context window.

**Where it fails:**
- Simulation 5: After 4-6 sub-agent calls for "why is competitor getting more views?", the main agent has received potentially 40-100 segment payloads in its context, each with 15-20 fields. Total: potentially 15,000-30,000 tokens of raw data that the main agent must summarize before synthesizing.

**Why this matters:**
1. Cost: Each synthesis turn for a complex query costs significantly more than a simple query because of the large input context.
2. Latency: Larger input context → longer TTFT.
3. Quality: LLMs are well-documented to "lose" information from long contexts (the "lost in the middle" problem). The most important data in a 20,000-token context window may be at position 10,000 — exactly where LLMs are worst.

**What's missing:** The sub-agent (SearchSkill) should do more pre-synthesis. Instead of returning raw segment payloads, it should return a structured summary:
- "Found 4 segments in 0:00-0:30. Shot types: MCU(×3), B-roll(×1). Music: absent throughout. Text overlays: 1 at 0:08 (center: '3 YEARS OF RESEARCH'). Cut events: 2 hard-cuts. Key transcript excerpt: segment 1 opens with 'Hey everyone...'"

This compresses the sub-agent's return from ~3,000 tokens to ~200 tokens, without losing the critical facts the main agent needs for synthesis.

---

### Gap 8 — The AnalysisSkill Is Undefined (MEDIUM)

**What it is:** The architecture mentions "AnalysisSkill" as a second skill alongside SearchSkill, but its definition, tools, and responsibilities are not specified.

**Where it fails:**
- Simulation 10: "Suggest improvements" is an analysis/reasoning task. SearchSkill can't do it — there's no search call that returns "improvement recommendations." AnalysisSkill should handle this, but its behavior is undefined.
- The 10-skill architecture in docs/chat_skill.md (HookDiagnosis, ProductionAudit, etc.) is also defined but not yet implemented in the codebase. The architecture spec describes a two-skill system (Search + Analysis) while the design document describes 10 skills. These are inconsistent.

**What's missing:** A decision on the skill architecture: are we building 2 skills or 10? If 2, AnalysisSkill needs a formal definition. If 10, the main agent needs to know how to route to the right one.

---

### Gap 9 — Streaming Breaks at Sub-Agent Boundaries (MEDIUM)

**What it is:** The proposed streaming shows "Using SearchSkill..." when the tool is called. But between the tool call start and tool return, there is a multi-second silent gap where nothing streams to the user.

**The streaming timeline for a complex query:**
```
T+0.0s: User sends message
T+0.5s: Main agent begins responding
T+0.8s: "Using SearchSkill..." streams to user
[SILENCE: sub-agent is executing internally]
T+4.5s: Sub-agent returns
T+5.0s: "Using SearchSkill..." streams again (2nd call)
[SILENCE]
T+9.0s: Sub-agent returns
T+9.5s: Main agent begins synthesis
T+10.0s-T+12.0s: Final answer streams token by token
```

**The UX problem:** Users see "Using SearchSkill..." then 3-4 seconds of nothing. They don't know if:
- The system is still working
- The system crashed
- They should wait

The LangChain event stream emits events at tool-call boundaries, not during sub-agent execution. The sub-agent's internal tool calls (search_segments) don't surface events to the main conversation stream.

**What's missing:** Progress events from inside the sub-agent, surfaced to the user. Options:
1. Have the sub-agent emit progress events ("Searching Qdrant for hook segments...") that get forwarded to the user-facing stream.
2. Show an animated "thinking" indicator with estimated completion time based on operation type.
3. Surface the sub-agent's final "I found X segments matching your criteria" before the main agent synthesizes.

---

### Gap 10 — No Token Budget or Sub-Agent Call Cap (LOW-MEDIUM)

**What it is:** The main agent can call `use_sub_agent_with_skill` an unlimited number of times. There is no maximum call count per user turn.

**Where it fails:**
- Simulation 5: For an open-ended question, the main agent might call the sub-agent 8-10 times, spending 5-7 minutes of compute and $0.50+ in API costs on a single user message.
- A malicious or confused user could craft a query that causes the main agent to loop indefinitely (if the main agent ever calls sub-agents based on the *outputs* of previous sub-agents, creating a chain).

**What's missing:** A hard cap: "You may call use_sub_agent_with_skill at most N times per user turn. If you need more, inform the user and offer to continue in a follow-up turn." N=3 is a reasonable default.

---

### Gap 11 — No Creator vs. Competitor Video Classification (MEDIUM)

**What it is:** The main agent must know which videos in the project belong to the creator vs. competitors. This determines how it frames answers ("your video" vs "competitor's video") and how it scopes sub-agent calls.

**Where it fails:**
- Simulation 11: "What is my most-used shot type?" — the main agent must exclude competitor videos from the GROUP_BY. If it can't distinguish creator vs. competitor videos, it mixes them.
- Simulation 5: "Why is my competitor's video doing better?" — the main agent needs to know which video_id is "yours" and which is "theirs."

**Current state:** The architecture injects "engagement metrics for loaded videos" but doesn't specify a classification scheme. The main agent likely infers creator ownership from video titles or creator_name fields — which is fragile (what if the creator's own video was uploaded by a different channel name, or the project has multiple creator channels?).

**What's missing:** An explicit "project manifest" in the main agent system prompt: a structured list with each video labeled as `role: "creator"` or `role: "competitor"` (or `role: "reference"`), along with title, UUID, and key metrics. This should be injected programmatically, not inferred by the LLM.

---

### Gap 12 — No Error Recovery in the Sub-Agent Loop (LOW)

**What it is:** If a sub-agent call fails (Qdrant timeout, network error, search returns unexpected format), there is no retry or fallback mechanism specified.

**Where it fails:**
- If Qdrant is down, the sub-agent's search_segments call throws an exception. The main agent receives an error from the sub-agent. It's unclear what the main agent does with this — the architecture doesn't specify error handling.

**What's missing:** A simple try/catch with 1 retry at the Qdrant call level, and a clear error message propagation to the main agent: "SearchSkill failed: Qdrant connection timeout. Results unavailable for this turn." The main agent should be able to surface this gracefully to the user rather than producing a broken or silent response.

---

## 4. Phase 3: Web Research Findings Per Gap

Web research was conducted on the top 7 most critical gaps. Findings are summarized below with source citations.

---

### Research 1 — Gap 1: Sequential Sub-Agent Latency + Single Tool Bottleneck

**Research query:** "agentic RAG sequential sub-agent calls latency optimization production 2025 2026"

**Key findings:**

**Latency reality in production:**  
Agentic RAG with 3-4 iteration loops takes 8-12 seconds vs. vanilla RAG at 1-2 seconds ([MarsDevs, 2026](https://www.marsdevs.com/guides/agentic-rag-2026-guide)). This aligns directly with the simulations above. The recommendation from production deployments: use Adaptive RAG to route simple queries to a fast path and only escalate to multi-agent for genuinely complex queries.

**Centralized orchestrator as bottleneck:**  
Research from arxiv (2604.22820, 2026) explicitly identifies centralized orchestration as a throughput bottleneck — if the orchestrator's LLM call takes 3 seconds and 20 workers are waiting, decomposition throughput is capped at ~6.7 tasks/second. For a single-user chat scenario, this means the user wait time is proportional to the number of required sub-agent calls, with no path to parallelism.

**The SOTCN/Federated CARA solution (2025):**  
The Agent-as-a-Tool paradigm and Self-Optimizing Tool Caching Network use RAG to dynamically discover and assemble stateful sub-agents on the fly, eliminatingTool Space Interference. This is directly relevant: instead of the orchestrator sequentially calling one sub-agent repeatedly with different skill names, a skill-routing layer could select the right agent type *before* calling it, enabling parallel dispatch.

**Practical recommendation from production systems:**  
LangGraph (recommended 2026 production stack) natively supports parallel node execution — running multiple sub-agents simultaneously and joining their outputs before synthesis. This is the primary counter to the sequential bottleneck.

**Application to CreatorJoy:**  
For any query requiring data from both Video A and Video B (comparisons, gap analysis), the two video-scoped sub-agent calls are completely independent and should run in parallel. LangGraph's parallel branches solve this directly. The sequential single-tool design should be replaced with a parallel-capable graph for multi-video queries.

---

### Research 2 — Gap 2: Ambiguous Query Intent Handling

**Research query:** "LLM orchestrator ambiguous query intent clarification vs inference production chatbot 2025"

**Key findings:**

**Production pattern — hybrid classifier:**  
Instacart's production "intent engine" (November 2025) uses a hybrid approach: fast embedding-based classifier (50-100ms) for known intents, falling back to LLM-based classification (1-2 seconds) only when confidence < 0.85. This prevents the "fire all sub-agents" failure mode by catching low-confidence classifications early and routing them to a clarification flow.

**Three-stage ambiguity pipeline:**  
Research from ACL 2025 (aclanthology.org) describes a three-stage pipeline: (1) identify inputs that benefit from clarification, (2) provide a clarifying QA pair corresponding to the gold interpretation, (3) use clarifying context in generation. The key insight: **not all ambiguous queries benefit equally from clarification**. "Make my video better" benefits enormously from clarification. "What shot types do I use?" doesn't need clarification even if slightly underspecified.

**Rasa's production finding (2025):**  
When queries are out-of-scope or ambiguous, a fallback LLM agent should ask *at most one* clarifying question or loop in a human — not fire multiple retrieval paths. The 2025 guidance: offer a constrained menu of options ("Do you mean X, Y, or Z?") rather than an open-ended "what do you mean?"

**Application to CreatorJoy:**  
The main agent system prompt should include a two-tier ambiguity rule:
1. If a query is missing a **video target** (no video named, ambiguous "my video"), ask ONE clarifying question: "Which video would you like me to analyze? [list ingested videos]"
2. If a query is missing a **dimension** (production? editing? content?), either ask one clarifying question *or* default to the most common question type for that creator based on prior conversation history. Don't fire all skills simultaneously.

---

### Research 3 — Gap 3: Video Not In Project + Graceful Degradation

**Research query:** "multi-agent system unhandled edge case graceful degradation LLM 2025 2026"

**Key findings:**

**MAST failure taxonomy (NeurIPS 2025):**  
The most-cited 2025 paper on multi-agent failure (arxiv 2503.13657, NeurIPS 2025 poster) identifies 14 failure modes across 1,600+ execution traces. The most catastrophic is "verification gap" — agents producing outputs without verifying the preconditions needed for those outputs to be valid. "Video not ingested → hallucinated analysis" is a textbook verification gap failure.

**Circuit breaker pattern:**  
The production recommendation (multiple sources, 2025-2026) is to implement circuit breakers that isolate agents before they can consume token budgets on invalid preconditions. For CreatorJoy, this means: before ANY sub-agent call, the main agent must run a precondition check: "Is the referenced video in the ingested video list? If no, halt and inform the user."

**Token budget and hard limits:**  
A related finding: agents in infinite loops or operating on bad preconditions can burn thousands of dollars in API credits in minutes ([Augment Code, 2026](https://www.augmentcode.com/guides/why-multi-agent-llm-systems-fail-and-how-to-fix-them)). The circuit breaker is both a UX protection and a cost protection.

**Application to CreatorJoy:**  
The circuit breaker for "video not in project" must be implemented as a deterministic pre-check (not LLM-based). The main agent system prompt includes the complete list of ingested video IDs. The application layer (not the LLM) should validate the user's referenced video against this list *before* the main agent generates a response. If it's not in the list: return a canned "not ingested" message instantly, without ever calling the LLM.

This is a case where the guard should live *outside* the LLM, not inside it — LLMs cannot reliably self-censor on precondition violations.

---

### Research 4 — Gap 4: Conversation Memory Compaction

**Research query:** "LLM conversation memory long context management agent compaction strategies production 2025 2026"

**Key findings:**

**Context drift kills agents:**  
The LogRocket 2026 analysis identifies context drift (not raw context exhaustion) as the primary failure mode in long-running LLM agent conversations — nearly 65% of enterprise AI failures in 2025 were attributed to context drift or memory loss during multi-step reasoning ([LogRocket, 2026](https://blog.logrocket.com/llm-context-problem/)).

**Summarization-based compaction:**  
The standard approach: when conversation history exceeds a threshold (typically 32k-100k tokens), summarize older portions with an LLM and replace them with a single summary message. Anthropic's own compaction API provides this as a production-ready capability for Claude. The key insight: preserve "key facts, decisions, user preferences, and tool call outcomes" — discard "redundant tool outputs" ([Microsoft Learn](https://learn.microsoft.com/en-us/agent-framework/agents/conversations/compaction)).

**ACON (2025):**  
The ACON algorithm (gradient-free context compression) achieves 26-54% reduction in peak token usage by identifying what information was critical in successful completions vs. what was safe to compress. This is relevant for CreatorJoy: the raw segment payloads from Qdrant (verbose, many fields) should be compressed in conversation history while the synthesized conclusions (shot type distribution, production observations) are preserved.

**Application to CreatorJoy:**  
Specific to this system: the conversation history stored in SQLite should store the *synthesized response* only (what the user sees), not the raw sub-agent outputs. The raw Qdrant payloads returned by sub-agents should never be persisted to conversation history — they served their purpose when the main agent synthesized from them, and don't need to be re-fed to the main agent on subsequent turns.

Implementation:
1. SQLite conversation_history table stores: `user_message`, `bot_response_final` (the user-visible text only)
2. Raw sub-agent outputs are ephemeral — they exist only in the current turn's working memory
3. After 20 turns, apply a compaction step: summarize turns 1-10 into a paragraph, replace those rows with the summary

---

### Research 5 — Gap 5: Situational Prompt Quality and Context Passing

**Research query:** "multi-agent chatbot situational prompt context passing between agents best practices 2025"

**Key findings:**

**Context engineering as the #1 job:**  
Vellum.ai's 2025 analysis identifies context engineering — "treating context as a first-class system with its own architecture, lifecycle, and constraints" — as the primary discipline for reliable multi-agent systems. The specific failure mode: unstructured multi-agent networks amplify errors up to 17.2x compared to single-agent baselines. When agent A's output is agent B's input without a structured handoff schema, errors compound rather than cancel.

**Structured handoff protocols:**  
Google's production multi-agent framework (Google Developers Blog) uses a four-component orchestration: (1) registry of available agents/capabilities, (2) router that maps tasks to agents, (3) state store for shared context, (4) supervisor for timeouts/retries. The critical element is the **state store** — shared context that both orchestrator and sub-agents can read, rather than one-directional situational prompts.

**OpenAI Agents SDK handoff pattern:**  
Agents carry conversation context through handoffs via an explicit schema: instructions, model reference, tools, and a list of agents it can hand off to. The context isn't free-form text — it's a structured payload.

**Application to CreatorJoy:**  
The situational prompt should be replaced with a structured handoff schema. Concretely, instead of a freeform text paragraph, the main agent writes a JSON object:
```json
{
  "user_goal": "...",
  "context_from_conversation": ["finding 1", "finding 2"],
  "task": {
    "operation": "FETCH | COUNT | GROUP_BY | SUM_duration",
    "video_ids": ["uuid1"],
    "filters": { "timecode_start_max_seconds": 30.0 },
    "fields_of_interest": ["shot_type", "transcript", "on_screen_text"]
  },
  "why": "..."
}
```
The SearchSkill sub-agent parses this schema, not a free-form paragraph. This eliminates the ambiguity and missing-context failure modes.

---

### Research 6 — Gap 9: Streaming and Sub-Agent Progress Visibility

**Research query:** "LLM agent streaming tool call events SSE user experience multi-step 2025 2026"

**Key findings:**

**SSE remains the dominant protocol:**  
Server-Sent Events are confirmed as the 2026 production standard for streaming LLM agent responses. LangChain's streaming system natively supports state-update events after each agent step, which can be forwarded to the user-facing stream ([LangChain streaming docs](https://docs.langchain.com/oss/python/langchain/streaming)).

**The 30-second silence problem:**  
Multiple sources confirm that 30 seconds of silence (or even 5 seconds with a spinner) is unacceptable UX — users assume the application froze ([Dev Community, 2025](https://dev.to/pockit_tools/the-complete-guide-to-streaming-llm-responses-in-web-applications-from-sse-to-real-time-ui-3534)). The solution: decouple long-running tasks from user-facing requests and stream progress updates.

**Multi-agent streaming complexity:**  
SSE wasn't built for multi-agent scenarios, but can be adapted with stream IDs, event typing, and multiplexed streams. Each sub-agent's progress can be a distinct named event stream that the frontend displays as a status indicator.

**Application to CreatorJoy:**  
Three-level streaming events should be emitted:
1. `main_agent_thinking`: "Analyzing your question..." (immediate, 0ms)
2. `skill_started`: "Searching for hook segments in Video A..." (at sub-agent tool call)  
3. `skill_progress`: "Found 4 segments, analyzing..." (from inside sub-agent after Qdrant returns)
4. `skill_complete`: "Hook analysis ready" (at sub-agent return)
5. `synthesizing`: "Comparing and writing your answer..." (before final synthesis)
6. Streaming final answer token by token.

This turns a 10-second wall-clock wait into a sequence of visible progress events, which research consistently shows improves perceived performance even when actual latency is unchanged.

---

### Research 7 — Gap 1/7: Multi-Agent Routing Failure Rates and Cascading Errors

**Research query:** "multi-agent LLM orchestrator routing failure modes wrong skill selection 2025 2026"

**Key findings:**

**Failure rates are high:**  
Multi-agent LLM systems fail between 41% and 86.7% on standard benchmarks, with the MAST taxonomy (NeurIPS 2025, arxiv 2503.13657) mapping 14 failure modes to three root categories: specification ambiguity (by far the largest category), coordination breakdowns, and verification gaps.

**Cascading routing errors:**  
A misclassified query cascades through multiple incorrect agents, compounding hallucinations and incorrect responses. In the CreatorJoy context: if the main agent routes a "production quality" query to SearchSkill with a semanticquery for "professional-looking segments" (Mode 2, nl_query) instead of a structural fetch of production fields (Mode 1), it will get high-scoring segments that *sound* professional in the transcript rather than segments with measurably professional lighting, audio, and camera work.

**Tool count and accuracy:**  
Once an agent has access to 15-20 tools, tool selection accuracy drops below 80%. CreatorJoy's sub-agent only has 1 tool (search_segments), which is correct — but the main agent's single tool is itself a complex interface (it takes skill_name + situational prompt, where both are LLM-generated and error-prone). The real tool count from the main agent's perspective is: "however many distinct tasks I need to call this one tool for" — which can be 6+ for complex queries.

**Application to CreatorJoy:**  
The routing decision (which skill, what situational prompt) happens entirely inside the main agent LLM. There is no deterministic routing layer. For known query patterns (jump cut count, engagement rate, hook comparison), the routing should be deterministic or at least validated by a fast classifier before reaching the expensive main agent LLM. A 50ms keyword classifier that catches "jump cut" → "structural COUNT query" prevents the main agent from ever attempting a semantic search for jump cuts.

---

## 5. Final Recommendations

These are concrete, prioritized changes. Organized as: KEEP, FIX, ADD. No hand-wavy suggestions — each item is specific.

---

### KEEP — These design decisions are correct

**1. Single tool on the main agent (`use_sub_agent_with_skill`)**  
The principle is right: the main agent should be a coordinator, not a data retriever. Keeping it to one conceptual tool prevents the main agent from doing too much. The problem is execution speed (sequential), not the concept.

**2. Engagement metrics injected into main agent system prompt**  
Avoids a sub-agent call for purely numerical queries (ER, view counts, like rates). This is the right pre-computation approach. Extend it to include duration, upload_date, platform, and a computed ER field (don't make the LLM compute ER).

**3. SearchSkill's three-mode search (structural/semantic/hybrid)**  
This is a strong, well-designed skill. The Mode 1 / Mode 2 / Mode 3 taxonomy with explicit field reference table is exactly right. Don't change this.

**4. Project ID + video IDs injected at runtime (not by LLM)**  
Correct security and correctness decision. The LLM should never be trusted to know the right UUID — it must be injected. Extend this discipline to all security-sensitive fields.

**5. SQLite for conversation history**  
Good choice. SQLite is fast, local, and simple. The problem isn't the storage mechanism — it's what gets stored. Fix that separately.

**6. Per-segment richness of the transcription schema**  
The 15-field-per-segment schema is what enables precise, citable answers. This is the core differentiator of the product. Don't simplify it.

---

### FIX — These design decisions are correct in concept but need specific changes

**1. Fix: Sequential sub-agent calls → Parallel for multi-video queries**

For any query requiring data from more than one video, the two sub-agent calls are independent and MUST run in parallel. Use LangGraph's parallel node execution:

```python
# Instead of:
result_a = use_sub_agent("SearchSkill", prompt_for_video_a)  # blocks 3s
result_b = use_sub_agent("SearchSkill", prompt_for_video_b)  # blocks 3s

# Use:
results = await asyncio.gather(
    use_sub_agent("SearchSkill", prompt_for_video_a),  # parallel
    use_sub_agent("SearchSkill", prompt_for_video_b),  # parallel
)  # total: 3s, not 6s
```

This halves the latency for all comparison queries (which are the highest-value queries in the product).

**2. Fix: Conversation history storage — store synthesized responses only**

The SQLite conversation_history table should store only what the user sees:
- `user_message`: the user's text
- `bot_response`: the final synthesized text the user received
- NOT the raw sub-agent outputs

Raw Qdrant payloads are ephemeral working memory, not conversation context. Never persist them.

Add a compaction trigger: after 15 turns, summarize turns 1-10 with a cheap LLM call and replace those rows with a summary row.

**3. Fix: Main agent system prompt must include explicit video manifest**

The system prompt must contain a structured, unambiguous video manifest:
```
AVAILABLE VIDEOS:
- Video ID: "uuid-A" | Title: "How I Built My Audience" | Creator: "YourChannel" | 
  Role: YOUR VIDEO | Views: 12,400 | ER: 3.2% | Duration: 8:12 | Uploaded: 2026-03-14
  
- Video ID: "uuid-B" | Title: "I Went From 0 to 100k Subscribers" | Creator: "CompetitorChannel" | 
  Role: COMPETITOR VIDEO | Views: 47,300 | ER: 5.5% | Duration: 12:07 | Uploaded: 2026-02-28

If a user references a video not listed here, DO NOT call any sub-agent. Tell them to ingest it first.
```

This directly fixes Gaps 3, 11, and the UUID-mapping problem from Simulation 2.

**4. Fix: Sub-agent return format — structured summary, not raw payloads**

The sub-agent (SearchSkill) should return a structured summary, not raw segment dumps:
```json
{
  "query_executed": { "mode": "structural", "operation": "FETCH", "filters": {...} },
  "result_count": 4,
  "video_id": "uuid-A",
  "timecode_range": "0:00 - 0:31",
  "key_findings": {
    "shot_types_observed": ["MCU", "B-roll"],
    "transcript_excerpts": [
      { "segment_id": 1, "timecode": "0:00", "text": "Hey everyone, so today..." }
    ],
    "on_screen_text": [
      { "segment_id": 2, "timecode": "0:08", "text": "3 YEARS OF RESEARCH", "position": "center" }
    ],
    "cut_events": [
      { "segment_id": 2, "timecode": "0:08", "type": "hard-cut" },
      { "segment_id": 3, "timecode": "0:15", "type": "hard-cut" }
    ],
    "music_present": false
  }
}
```

This reduces the main agent's input context by ~90% for data-heavy queries while preserving everything the main agent needs for synthesis.

**5. Fix: Ambiguity handling — mandatory single clarifying question rule**

Add to main agent system prompt:
```
AMBIGUITY RULE:
If the user's query does not specify:
  (a) which video(s) to analyze, OR
  (b) which dimension to focus on (production, editing, content, engagement)
Then ask EXACTLY ONE clarifying question and wait for the response.
Do NOT call use_sub_agent_with_skill on an ambiguous query.
Format: "To help you best, I need to know: [single question]. [optional: list of choices]"
```

---

### ADD — These capabilities are missing and must be built

**1. ADD: Deterministic pre-check before any LLM call**

Add an application-layer guard (not LLM-based) that runs before the main agent LLM is invoked:
1. Parse the user's message for video references (URL patterns, title substrings, "my video" / "competitor's video" keywords).
2. Check each reference against the ingested video manifest.
3. If any reference is unrecognized: return a canned "this video isn't ingested yet" message immediately. Do NOT call the LLM.

This is the circuit breaker for Gap 3. It costs 0 tokens and 0 LLM latency.

**2. ADD: Sub-agent call cap**

Add to main agent system prompt:
```
CALL LIMIT: You may call use_sub_agent_with_skill at most 3 times per user message.
If you believe you need more than 3 calls to answer completely, tell the user which parts 
you'll answer and ask if they want to continue with the rest in the next message.
```

And enforce this programmatically: the LangChain agent orchestrator should count tool calls and stop after 3, returning whatever has been gathered so far.

**3. ADD: Progress streaming events from sub-agents**

The user-facing event stream should emit at minimum:
- `skill_started` event with the skill name and a human-readable description of what's being searched ("Searching for segments in your video from 0:00–0:30...")
- `skill_progress` event after Qdrant returns (before LLM formats the result): "Found N segments matching your criteria..."
- `skill_complete` event at sub-agent return

This requires the sub-agent to emit events that are forwarded to the top-level SSE stream — implementable with LangChain's streaming callback system.

**4. ADD: SAMPLE operation in SearchSkill**

Add a 5th operation to search_segments: `SAMPLE`, which returns `n` segments distributed across the video's timeline (beginning, middle, end). Concretely: divide the video into `n` equal time windows and return the first segment from each window.

This enables ProductionAudit and SeriesAnalysis patterns without requiring multiple FETCH calls or context-dumping all segments.

**5. ADD: Structured situational prompt schema**

Replace free-form text situational prompts with a JSON schema. The main agent writes a structured JSON object; the sub-agent parses and validates it before executing. The schema enforces: video_ids are always present, operation type is always specified, fields of interest are enumerated. This eliminates the "under-specified situational prompt" failure mode.

**6. ADD: Clarification for "AnalysisSkill" or adopt the 10-skill architecture**

There is an inconsistency between the proposed two-skill architecture (Search + Analysis) and the richer 10-skill design in docs/chat_skill.md. A decision must be made:

- **Option A (recommended):** Adopt the 10-skill architecture from chat_skill.md. Each skill has a focused role and tool set. The main agent's routing decision becomes "which skill?" rather than "what situational prompt?" The skills enforce citation discipline, search modes, and output format without the main agent having to prescribe them. This aligns with the MAST research finding that specialized, focused agents outperform general agents with large tool sets.

- **Option B:** Keep two skills but write a complete AnalysisSkill definition (what it does, what tools it has, when it's used vs. SearchSkill). This is faster to build but will hit the "AnalysisSkill does what exactly?" problem immediately.

**7. ADD: Pre-computed ER fields in engagement metrics injection**

Do not store raw like_count, view_count, comment_count in the main agent system prompt and expect the LLM to compute ER. Pre-compute and store:
- `er_views` = (likes + comments) / views (rounded to 2 decimal places)  
- `like_rate` = likes / views
- `duration_formatted` = "MM:SS"
- `views_vs_followers_ratio` = views / channel_followers

Compute these at ingestion time and store in SQLite. Inject the pre-computed values into the main agent system prompt. The LLM should never do arithmetic on production data.

---

### Priority order for implementation

| Priority | Change | Why |
|----------|--------|-----|
| P0 | Deterministic video manifest + pre-check guard | Prevents hallucination on unknown videos — catastrophic if shipped without |
| P0 | Explicit ambiguity-handling rule in main agent system prompt | Prevents 20-second blast on vague queries |
| P1 | Structured sub-agent return format (summaries, not raw payloads) | Reduces main agent context by 90%, improves synthesis quality |
| P1 | Parallel sub-agent execution for multi-video queries | Halves latency on the highest-value query type |
| P1 | Store only synthesized responses in SQLite (not raw sub-agent outputs) | Prevents context window blowup after 20+ turns |
| P2 | Sub-agent call cap (3 per turn, enforced programmatically) | Cost and latency protection |
| P2 | Progress streaming events from sub-agents | UX quality for complex queries |
| P2 | Pre-computed ER and duration fields in main agent context | Prevents LLM arithmetic errors |
| P3 | SAMPLE operation in SearchSkill | Enables ProductionAudit/SeriesAnalysis efficiently |
| P3 | Structured situational prompt JSON schema | Eliminates under-specification failure mode |
| P3 | Adopt 10-skill architecture (or formally define AnalysisSkill) | Long-term quality — decide before building AnalysisSkill |

---

## Summary

The proposed architecture is directionally correct: a coordinating main agent with a single conceptual tool, skill-specialized sub-agents, rich structured Qdrant data, and SQLite conversation memory. These are sound design decisions.

The critical failure modes are:

1. **No guard against un-ingested video references** — this can cause hallucination, which is unrecoverable for user trust.
2. **No ambiguity resolution discipline** — vague queries cause expensive, slow, and often wrong multi-sub-agent blasts.
3. **Sequential sub-agent calls for parallel-eligible work** — comparison queries (the product's highest-value feature) will feel slow.
4. **Raw Qdrant payloads in main agent context** — context bloat and synthesis quality degradation over multi-turn conversations.
5. **No conversation memory compaction** — time bomb at 20+ turns.

None of these are architectural blockers. They are all fixable before or during the first production build. The core architecture — sub-agent delegation, Qdrant hybrid search, rich per-segment schema — is correct and does not need to change.

---

*Document written: 2026-05-09*  
*For the CreatorJoy chatbot pre-build validation phase*
