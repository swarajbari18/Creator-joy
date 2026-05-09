# Rich Video Transcription — Implementation Notes

## Files Created

### `backend/creator_joy/transcription/__init__.py`
Package marker. Exports: `TranscriptionService`, `TranscriptionSettings`, `TranscriptionRecord`, `TranscriptionStatus`.

### `backend/creator_joy/transcription/models.py`
Data models and settings.

- `TranscriptionStatus(StrEnum)` — `pending | processing | completed | failed`
- `TranscriptionRecord(frozen dataclass)` — one row from the `transcriptions` SQLite table
- `TranscriptionSettings(frozen dataclass)` — configures storage root, database filename, Gemini model name, temperature, file poll interval/timeout. `gemini_model` reads `GEMINI_MODEL` env var at construction (default: `gemini-3-flash-preview`). `database_path` is a `@property`.

### `backend/creator_joy/transcription/schema.py`
Pydantic model tree for the Rich Video Transcription JSON.

**Key design:** All string fields use plain `str` (not `Literal` enums) so Gemini can write `[unclear]` or `[inaudible]` without validation errors.

Key models:
- `TranscriptionPayload(speakers, segments)` — the portion the LLM generates. Its JSON schema is injected into the prompt via `TranscriptionPayload.model_json_schema()`.
- `RichVideoTranscription(...)` — complete assembled document including code-filled document-level fields.
- `VideoSegment` includes `observable_summary: str` (Principle 5 from multimodal research) — anchors Gemini to facts before filling per-field values.

### `backend/creator_joy/transcription/database.py`
SQLite ops for `transcriptions` table. Opens the **same `creator_joy.sqlite3`** as `IngestionDatabase`. The `transcriptions` table foreign-keys on `videos.id`.

Methods: `create_or_reset_transcription()`, `update_transcription_status()`, `get_transcription()`, `get_transcription_for_video()`.

Patterns mirror `IngestionDatabase` exactly: context manager connection, `row_factory`, `PRAGMA foreign_keys = ON`, UTC ISO timestamps.

### `backend/creator_joy/transcription/transcriber.py`
Core Gemini interaction. Uses `google-genai` (File API upload) and `langchain-google-genai` (inference).

**Call flow inside `GeminiTranscriber.transcribe()`:**
1. Upload file via `genai.Client().files.upload()` → poll until `ACTIVE` → raise on timeout
2. Build prompt: system persona + focus anchor + video context + rules + field routing + explicit JSON schema + `OUTPUT JSON ONLY`
3. Call `ChatGoogleGenerativeAI.invoke()` → raw string response
4. `_parse_json_response()` — 3-step fallback (direct parse → strip backticks → LLM fix pass → raise loudly)
5. `TranscriptionPayload.model_validate()` — Pydantic validation
6. Delete uploaded Gemini file in `finally` block

**Why no `.with_structured_output()`:** Gemini has a quirk where LangChain's structured output abstraction is unreliable. Explicit JSON schema in prompt + "OUTPUT JSON ONLY" is what works.

**Message ordering — Principle 1 (`multimodal-prompting-research.md`):**
```python
# Video file FIRST, text instructions AFTER
message = HumanMessage(content=[
    {"type": "file_uri", "file_uri": file_uri, "mime_type": "video/mp4"},  # VIDEO FIRST
    {"type": "text", "text": prompt},                                        # TEXT AFTER
])
```
Reversing this degrades model attention on visual content.

**Prompt constants and what each addresses (all sourced from the research doc):**

| Constant | Research source | Failure prevented |
|---|---|---|
| `_SYSTEM_PROMPT` | Principle 2 — Documentarian persona | Model switching to analyst/evaluator mode |
| `_FOCUS_INSTRUCTION` | Principle 3 — Focus-on-Vision anchor (exact wording) | Failure Mode 2: modal bias — model writes generic expected values instead of what it actually observes |
| Chronological order rule in `_RULES` | Failure Mode 1 prevention | Temporal hallucination — events recorded out of order or mismatched to wrong timecode |
| `speaker_id` instruction in `_FIELD_ROUTING` | Failure Mode 3 prevention | Cross-modal speaker mismatch — voice attributed to wrong visible person |
| Verbatim override in `_FIELD_ROUTING` | Part 5 "Verbatim Override" technique | Transcript paraphrased instead of exact spoken words |

### `backend/creator_joy/transcription/service.py`
Orchestration. `TranscriptionService` wires together `IngestionDatabase`, `TranscriptionDatabase`, and `GeminiTranscriber`.

**`transcribe_video(video_id)` flow:**
1. Look up `VideoRecord` → raise if not found
2. Find `VideoFileKind.VIDEO` path → raise if ingestion incomplete
3. Load `metadata.json` from disk
4. Create/reset transcription row → PROCESSING
5. Call transcriber → `TranscriptionPayload`
6. Assemble `RichVideoTranscription`: fill document-level fields from `VideoRecord` + `metadata.json` by code; `speakers`+`segments` from LLM
7. Write `transcription.json` to video directory
8. Update status to COMPLETED; on exception → FAILED + re-raise

### `backend/tests/dev_test_transcription.py`
End-to-end test. Set `VIDEO_ID` at top to use an existing ingested video, or `INGEST_URL` to ingest + transcribe fresh.

### `backend/.env.example`
Template for all env vars. Copy to `.env`, fill values, source.

### `backend/requirements.txt`
Added: `langchain>=0.3.0`, `langchain-google-genai>=4.0.0`, `google-genai>=1.50.0`, `pydantic>=2.0.0`

---

## How to Run

```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt       # first time only

cp .env.example .env
# Fill in GOOGLE_API_KEY in .env

export $(grep -v '^#' .env | xargs)
python -m tests.dev_test_transcription
```

Expected output: upload/polling logs → Gemini response → JSON parse → `transcription.json` on disk → SQLite row COMPLETED → first 3 segments printed.

see the transcript on the terminal
```
python3 -c "
import json

data = json.load(open('/home/swarajbari/Projects/Creator-joy/backend/downloads/projects/fdb0d91b-8e8e-4fe3-87ff-1fc4fc89ffde/videos/c8604c66-2a5d-4ce4-96b8-43186fad1e46/transcription.json'))

for s in data['segments']:
    t = s['speech']['transcript'].strip()

    if t and t not in ('[inaudible]', '[unclear]', ''):
        print(f\"[{s['timecode_start']}] {t}\")
"
```
---

## LangSmith Setup

1. Sign up at https://smith.langchain.com (free: 5,000 traces/month)
2. Settings → API Keys → create key
3. In `.env`: set `LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_API_KEY=<key>`, `LANGCHAIN_PROJECT=creator-joy`
4. Re-source env and run — traces appear automatically at smith.langchain.com

---

## Output Location

```
backend/downloads/projects/{project_id}/videos/{video_id}/
  source_video.mp4
  audio.mp3
  metadata.json
  transcription.json    ← NEW
```

`creator_joy.sqlite3` now also has a `transcriptions` table.

---

## Call Graph

```
dev_test_transcription.py
  └─ TranscriptionService(settings)
        ├─ IngestionDatabase(db_path)        ← reads videos/video_files
        ├─ TranscriptionDatabase(db_path)    ← creates/manages transcriptions table
        └─ GeminiTranscriber(settings)       ← validates GOOGLE_API_KEY

  └─ TranscriptionService.transcribe_video(video_id)
        ├─ IngestionDatabase.get_video()
        ├─ IngestionDatabase.list_video_files()
        ├─ TranscriptionDatabase.create_or_reset_transcription()
        ├─ GeminiTranscriber.transcribe(video_path, video_record)
        │     ├─ genai.Client().files.upload()      [google-genai]
        │     ├─ poll until ACTIVE
        │     ├─ ChatGoogleGenerativeAI.invoke()    [langchain-google-genai]
        │     ├─ _parse_json_response()             [3-step fallback]
        │     └─ TranscriptionPayload.model_validate()
        ├─ assemble RichVideoTranscription (code fills doc-level fields)
        ├─ write transcription.json
        └─ TranscriptionDatabase.update_transcription_status(COMPLETED)
```

---

## If JSON Parsing Fails (All 3 Attempts)

`RuntimeError` includes the raw Gemini response and the LLM-fixed response. Check:
1. Did the file upload + processing succeed? Look for `ACTIVE` state in logs.
2. Is the video too long for Gemini's context window? Try a shorter video first.
3. Check LangSmith traces for the full request/response.
