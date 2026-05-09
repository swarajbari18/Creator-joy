# Multimodal Prompting Research
## How to prompt Gemini to produce a Rich Video Transcription

---

## The Purpose

Gemini receives a video. We want it to output a structured JSON document that faithfully records everything observable in that video — speech, visuals, production, audio, overlays, editing — timestamped and segmented. That document gets stored in the vector database. The chatbot queries it later.

Gemini is not being asked to analyze or evaluate. It is being asked to observe and record.

This document covers how to prompt Gemini to do that correctly.

---

## Part 1: How Gemini Actually "Sees" Video

Before writing any prompt, you need to understand what the model physically receives.

### The 1 FPS Sampling Reality

Gemini samples video at **1 frame per second by default**. Not 24fps. Not 30fps. One frame, per second.

This means:
- A 10-minute video = 600 frames Gemini actually sees
- A fast cut sequence (cuts every 0.5s) = Gemini may MISS ENTIRE SHOTS
- B-roll appearing for less than 1 second may be invisible to the model

**For our use case:** When capturing editing events (cut types, transitions), you need to **increase the FPS** or Gemini will miss cuts entirely. For slow talking-head content, 1fps is fine. For fast-cut YouTube content, set 2–4fps.

```python
# Override default 1fps sampling
videoMetadata = {
    "fps": 4,  # for fast-cut content
    "start_offset": "0s",
    "end_offset": "600s"
}
```

### Token Costs (Practical Constraints)

| Media Type | Token Rate | Implication |
|---|---|---|
| Video (standard res) | ~300 tokens/second | 1hr video ≈ 1.08M tokens |
| Video (low res) | ~100 tokens/second | 3hr video fits in 1M context |
| Audio only | 32 tokens/second | Very cheap |
| Per frame | 258 tokens (standard) / 66 tokens (low res) | |

**For our use case:** A 10-minute video at standard res = ~180K tokens for the video. That leaves ~820K tokens for your prompt, schema, and JSON response. Fine for most creator videos. For 30-minute videos, switch to low resolution mode.

### Context Window Limits

| Model | Context Limit | Max Video Length |
|---|---|---|
| Gemini 2.5 Flash | 1M tokens | ~1hr (standard) or ~3hrs (low res) |
| Gemini 2.5 Pro | 1M tokens | Same |

### File Input Methods

- **YouTube URL (Preview):** Easiest for our use case — no upload, no cost during preview, public videos only
- **File API:** Required for >20MB files, repeated analysis, or non-YouTube URLs
- **Inline data:** Only for <100MB one-off inputs

---

## Part 2: Why Multimodal Prompting Is Fundamentally Different From Text Prompting

### The 5 Ways It Differs

**1. Temporal grounding is required**
Text prompts have no notion of time. For video, without explicit timestamp instructions, the model produces a flat narrative with no temporal structure — useless for our segment-based schema.

> Wrong: "Describe this video"
> Right: "For each segment, record observations using MM:SS timecodes. Create a new segment entry when any observable element changes."

**2. Modality routing is required**
The model processes visual, audio, and on-screen text simultaneously. Without instructions telling it which modality to populate which field from, it defaults to speech and under-records visual information.

> Wrong: "Fill in all fields"
> Right: "For the `frame` field, observe only what is visually in the frame. For the `speech` field, record only what is verbally spoken. For the `audio` field, describe only non-speech audio."

**3. You must fight modal bias**
The model has strong training-data priors. If you show it a YouTube video, it will describe what it EXPECTS YouTube videos to look like — not what IS in your specific video. It may say "ring light" because most YouTubers use ring lights, even if this creator uses window light.

> Prevention: "Base every field value exclusively on what you directly observe in this specific video. Do not infer from typical videos of this type."

**4. Uncertainty flagging is mandatory**
With multimodal, the model hallucinates with equal confidence whether it's right or wrong. Give it an explicit escape hatch.

> Add to every prompt: "If any element is unclear, inaudible, or not visible, write [unclear] or [inaudible]. Do not guess to fill a field."

**5. Over-describing what's visible wastes tokens AND biases output**
In text prompting, more context helps. In multimodal prompting, if you describe the video in your prompt ("this is a YouTube creator talking about fitness"), the model anchors on your description instead of looking at the actual video. Your prompt should only specify WHAT fields to fill and HOW to fill them — never describe what you expect to find.

---

## Part 3: The 7 Principles of Multimodal Prompt Design for Data Capture

### Principle 1: Media First, Instructions After
Always place the video BEFORE the text prompt in the API call.

```python
contents = [
    Part.from_uri(uri=video_url, mime_type="video/mp4"),  # VIDEO FIRST
    "Your capture instructions here..."                    # TEXT AFTER
]
```

### Principle 2: Assign a Documentarian Persona, Not an Analyst Persona

```
System instruction:
"You are a meticulous video documentarian. Your job is to observe 
and record — not evaluate or interpret. You produce structured 
transcription documents that faithfully capture everything visible 
and audible in a video. You do not add meaning to observations. 
You record what is there."
```

Note: "documentarian" and "transcriptionist" produce better data-capture output than "analyst" or "expert." The persona word matters.

### Principle 3: Use "Focus-on-Vision" Anchoring
This is a specific technique from Google's own Gemini team that "significantly reduced inconsistencies." Add it before any capture instructions.

> "Look carefully and thoroughly at the actual content of this video. Base every field value on what you directly observe in this specific video, not on what you would expect a typical video of this type to contain."

### Principle 4: Specify Timestamp Format Explicitly
Gemini 2.0 was specifically trained on `MM:SS` format. Gemini 2.5 also understands `H:MM:SS`.

> "Use MM:SS timecode format for all `timecode_start` and `timecode_end` fields."

### Principle 5: Reasoning Before Each Segment Entry
Before filling any segment's fields, ask Gemini to write a one-line factual description of what is happening in that segment. This anchors the model to the actual content before it populates individual fields.

```json
{
  "timecode_start": "00:04",
  "observable_summary": "Speaker holds up printed paper, cut from previous talking-head shot",
  "speech": { ... },
  "frame": { ... }
}
```

The `observable_summary` field (not analysis — just a plain "what is happening") dramatically reduces field-level hallucination by grounding the model before it fills each individual field.

### Principle 6: Data Decoupling via Schema Fields
The schema structure IS the prompting technique. Each field in the Rich Video Transcription Schema is a separate concern. The model fills them independently. This prevents any one observable dimension (usually speech) from dominating the capture.

Wrong approach: "Describe what's happening in this segment"  
Right approach: Pass the full JSON schema and ask Gemini to populate each field from the appropriate modality.

### Principle 7: Use Structured Output Schema (response_schema)
Always use `response_mime_type="application/json"` with an explicit `response_schema` matching the Rich Video Transcription Schema. This constrains Gemini's output to the exact structure and prevents:
- Narrative paragraphs appearing instead of JSON
- Field names drifting across segments
- Analysis text appearing in data fields

```python
generation_config = GenerationConfig(
    response_mime_type="application/json",
    response_schema=RICH_VIDEO_TRANSCRIPTION_SCHEMA,
    temperature=0.1  # Low temp — this is data capture, not creative generation
)
```

---

## Part 4: Failure Modes in Data Capture (And How to Prevent Them)

### Failure Mode 1: Temporal Hallucination
**What happens:** Model records events in wrong order, invents visual elements that didn't appear at that timestamp, or mismatches what was said with when it was said.
**Prevention:** Ask for strictly sequential output: "Record segments in strict chronological order. Each entry must correspond to a specific, verifiable moment in the video."

### Failure Mode 2: Modal Bias (Generic vs. Specific)
**What happens:** Model writes `"lighting: 3-point"` because most YouTube videos use 3-point lighting, even when looking at window-lit content.
**Prevention:** "Focus-on-Vision" anchor. Add: "Do not record typical or assumed values. Only record what you can directly observe."

### Failure Mode 3: Cross-Modal Speaker Mismatch
**What happens:** Confident male voice attributed to visible female speaker. Speaker_A and Speaker_B labels get swapped mid-document.
**Prevention:** "For the `speaker_id` field, identify the speaker using BOTH who is visibly speaking (lip movement, facing camera) AND the voice characteristics. If these conflict, record [unclear]."

### Failure Mode 4: Hallucinated Field Values
**What happens:** Model invents a text overlay that wasn't there, describes an animation that didn't happen, fills `transcript` with paraphrased rather than verbatim text.
**Prevention:** Uncertainty flagging + low temperature. Add: "Write [unclear] for any field you cannot directly verify. Write [inaudible] for speech you cannot clearly hear. Never paraphrase in the `transcript` field — verbatim only."

### Failure Mode 5: Data Degradation in Long Videos
**What happens:** Field quality drops after ~30 minutes. `shot_type` entries become generic, `transcript` loses verbatim accuracy, segments become longer and less granular.
**Prevention:** For videos >15 minutes, use context caching and segment the capture into logical chapters. Run a separate Gemini call per chapter, then merge outputs.

---

## Part 5: Techniques That Work for Data Capture

### The "Verbatim Override"
Use the word "verbatim" explicitly in the transcript field instruction. It outperforms "exact words," "word for word," or "do not summarize."

> Field instruction: "Record speech VERBATIM. Include 'um,' 'uh,' false starts, and repeated words. Do not clean up or paraphrase."

### The "Timecode" Vocabulary
"Timecode" produces more consistent MM:SS formatting than "timestamp" or "time marker." The model was trained on professional transcription vocabulary.

### Metadata Enrichment
Adding known metadata to the prompt dramatically improves speaker identification and reduces hallucination of context-specific details.

> "This video is from the YouTube channel [channel name]. The creator's name is [name]."

### Modality-Specific Field Instructions
For each field group in the schema, specify which modality to observe:

```
For the `frame` and `background` and `lighting` fields: 
  observe only the visual content of the frame.

For the `speech.transcript` field: 
  record only verbatim spoken dialogue from the audio track.

For the `audio` fields: 
  observe only non-speech audio — music, sound effects, ambient sound.

For the `on_screen_text` fields: 
  record only text visible in the frame itself, not spoken text.
```

### Context Caching for the Same Video
If running the transcription in multiple passes (e.g., first pass gets speech and structure, second pass focuses on visual production details), cache the video after the first call.

- 90% token cost reduction on subsequent passes
- Implicit caching in Gemini 2.5 — automatic, no code change needed

### Low Resolution Mode
For standard talking-head content (no dense visual detail, no fast cuts), low resolution mode produces nearly identical transcription quality at 1/3 the token cost.

---

## Part 6: The Gemini Prompt for Creator-Joy Rich Video Transcription

```
SYSTEM INSTRUCTION:
"You are a meticulous video documentarian. Your job is to observe 
and record everything in a video as structured data. You do not 
evaluate, judge, or interpret. You record only what is directly 
observable. When uncertain, you write [unclear]."

FOCUS INSTRUCTION (add before schema):
"Look carefully at the actual content of this specific video. 
Every field value must be grounded in what you directly observe 
in this video. Do not use assumed or typical values."

USER PROMPT (placed AFTER the video in the API call):

Produce a Rich Video Transcription for this video.

Rules:
- Use MM:SS timecode format throughout
- Create a new segment entry whenever any observable element changes 
  (new cut, new speaker, overlay appears, camera movement, music shift)
- Populate each field from its correct modality (see instructions per field below)
- Write VERBATIM speech — do not paraphrase or clean up
- Write [unclear] for any field you cannot directly verify
- Write [inaudible] for speech you cannot clearly hear
- Do not skip segments to save tokens

Field instructions:
- speech.transcript: verbatim spoken words from audio only
- frame fields: observe only what is physically in the video frame
- background fields: observe only what is visible behind the subject
- lighting fields: observe only visible light sources and their observable effects
- on_screen_text: record only text visible in the frame — exact text, position, color, animation
- graphics_and_animations: record any visual elements added in post
- editing fields: record cut events and transition effects observable at segment boundaries
- audio fields: observe only non-speech audio — music, SFX, ambient
- production_observables: record only directly observable production details

Output the complete Rich Video Transcription as JSON matching this schema:
[PASTE FULL SCHEMA HERE]
```

---

## Part 7: One Prompt vs. Multi-Pass — The Decision Rule

Try single-prompt first. Evaluate data quality on these criteria:

| Data Quality Check | If Passes | If Fails |
|---|---|---|
| `transcript` fields are verbatim, not paraphrased | Keep single prompt | Add stronger verbatim instruction + separate transcription pass |
| `on_screen_text` captures all visible overlays accurately | Keep | Increase FPS; add modality routing instruction for overlays |
| `frame.shot_type` values are specific to this video, not generic | Keep | Add stronger "Focus-on-Vision" anchor |
| `lighting` and `background` values are specific, not assumed | Keep | Add "only record directly observable values" instruction |
| `editing.cut_event` captures all cuts | Keep | Increase FPS setting to 2–4 |
| Data quality holds for full video duration | Keep | Segment video; run per-chapter with context caching |

**The rule:** Only split into multi-pass if a specific field type is failing. Start with one prompt.

---

## Sources

- [Video Understanding — Gemini API Official Docs](https://ai.google.dev/gemini-api/docs/video-understanding)
- [Multimodal Prompting with Gemini: Audio — Google Cloud](https://googlecloudplatform.github.io/applied-ai-engineering-samples/genai-on-vertex-ai/gemini/prompting_recipes/multimodal/multimodal_prompting_audio/)
- [Multimodal Prompting with Gemini: Video — Google Cloud](https://googlecloudplatform.github.io/applied-ai-engineering-samples/genai-on-vertex-ai/gemini/prompting_recipes/multimodal/multimodal_prompting_video/)
- [Unlocking Multimodal Video Transcription — Part 4: Prompt Crafting](https://medium.com/google-cloud/unlocking-multimodal-video-transcription-with-gemini-part4-3381b61aaaec)
- [Unlocking Multimodal Video Transcription — Part 7: Analysis & Optimizations](https://medium.com/google-cloud/unlocking-multimodal-video-transcription-with-gemini-part7-74ee997d2096)
- [Technical Report: Multimodal Inconsistencies in Google Gemini](https://medium.com/@jabbalarajamohan/technical-report-multimodal-inconsistencies-in-google-gemini-9b15bcc81fb4)
- [Multimodal AI Prompting: Complete 2026 Guide — SurePrompts](https://sureprompts.com/blog/ai-multimodal-prompting-complete-guide-2026)
