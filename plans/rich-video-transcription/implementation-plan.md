# Rich Video Transcription — Implementation Plan

## What This Is

Takes a downloaded video file (from the ingestion pipeline), uploads it to Gemini via the File API, calls Gemini 3 Flash via LangChain with a structured prompt, parses the JSON response, validates it with Pydantic, assembles the full Rich Video Transcription by combining LLM output with yt-dlp metadata we already have, saves `transcription.json` to disk, and tracks status in SQLite.

---

## Files to Create

```
backend/creator_joy/transcription/
    __init__.py
    models.py           ← TranscriptionStatus, TranscriptionRecord, TranscriptionSettings
    schema.py           ← Pydantic model tree (used for validation, NOT structured output)
    database.py         ← SQLite ops for `transcriptions` table (same DB file as ingestion)
    transcriber.py      ← File upload + Gemini call + JSON parse
    service.py          ← Orchestration

backend/tests/dev_test_transcription.py
backend/.env.example
```

**Modify:** `backend/requirements.txt`

---

## models.py

```python
class TranscriptionStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass(frozen=True)
class TranscriptionRecord:
    id: str
    video_id: str
    status: TranscriptionStatus
    transcription_path: str | None
    error_message: str | None
    gemini_model: str | None
    created_at: str
    updated_at: str

@dataclass(frozen=True)
class TranscriptionSettings:
    storage_root: Path = Path("downloads")
    database_filename: str = "creator_joy.sqlite3"
    gemini_model: str = field(default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview"))
    temperature: float = 0.1
    file_poll_interval_seconds: int = 5
    file_poll_timeout_seconds: int = 300

    @property
    def database_path(self) -> Path:
        return self.storage_root / self.database_filename
```

---

## schema.py

Pydantic model tree for the Rich Video Transcription. Key decisions:

- All string fields use plain `str` — not `Literal` enums — so Gemini can write `[unclear]` or `[inaudible]` without validation failure
- `VideoSegment` includes `observable_summary: str` — one factual sentence anchoring Gemini before it fills individual fields (Principle 5, multimodal-prompting-research.md)
- A separate smaller model `TranscriptionPayload(speakers, segments)` is what we send to the LLM — we do NOT ask the LLM to generate fields we already have from yt-dlp
- The root model `RichVideoTranscription` contains everything including document-level fields filled by code

Models: `SpeakerInfo`, `SpeechData`, `FrameData`, `BackgroundData`, `LightingData`, `OnScreenTextEntry`, `OnScreenTextData`, `GraphicsEntry`, `GraphicsData`, `CutEvent`, `EditingData`, `MusicData`, `SoundEffectEntry`, `SoundEffectsData`, `AudioData`, `ProductionObservables`, `VideoSegment`, `TranscriptionPayload`, `RichVideoTranscription`

---

## database.py — TranscriptionDatabase

Opens the same SQLite file as IngestionDatabase. Manages:

```sql
CREATE TABLE IF NOT EXISTS transcriptions (
    id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    status TEXT NOT NULL,
    transcription_path TEXT,
    error_message TEXT,
    gemini_model TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
);
```

Methods: `create_or_reset_transcription(video_id)`, `update_transcription_status(id, status, ...)`, `get_transcription(id)`, `get_transcription_for_video(video_id)`, `_transcription_from_row(row)`.

Same patterns as IngestionDatabase: `with self._connect() as conn`, `row_factory`, PRAGMA foreign_keys, UTC ISO timestamps.

---

## transcriber.py — GeminiTranscriber

### Step 1: File Upload

```python
client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
uploaded = client.files.upload(file=str(video_path))
# Poll until ACTIVE — raise loudly on timeout
```

Always delete the uploaded file in a `finally` block.

### Step 2: Prompt Construction

Includes:
- System: documentarian persona (from multimodal-prompting-research.md)
- Focus anchor: "Look carefully at the actual content of this specific video..."
- Context injection: title + creator_name from yt-dlp metadata
- Instructions: verbatim transcript, MM:SS timecodes, [unclear] rules, no skipping segments
- Modality routing per field group
- `json.dumps(TranscriptionPayload.model_json_schema(), indent=2)` — schema included explicitly in prompt
- Final line: **`OUTPUT JSON ONLY`** (in caps — required for reliable Gemini JSON output)

### Step 3: LangChain Call

```python
llm = ChatGoogleGenerativeAI(model=settings.gemini_model, temperature=settings.temperature)
message = HumanMessage(content=[
    {"type": "text", "text": prompt},
    {"type": "file_uri", "file_uri": uploaded.uri, "mime_type": "video/mp4"},
])
response = llm.invoke([SystemMessage(content=system_prompt), message])
raw_text = response.content
```

> **Do NOT use `.with_structured_output()`** — it does not work reliably with Gemini models. Use explicit JSON schema in the prompt instead.

### Step 4: JSON Parsing (3-step fallback)

```
Attempt 1: json.loads(raw_text)
Attempt 2: strip ```json...``` backtick wrapper, then json.loads()
Attempt 3: send raw_text + parse error back to LLM for fix, then json.loads()
If all fail: raise RuntimeError(f"JSON parse failed after 3 attempts. Raw response:\n{raw_text}")
```

### Step 5: Pydantic Validation

```python
payload = TranscriptionPayload.model_validate(parsed_dict)
```

---

## service.py — TranscriptionService

`transcribe_video(video_id: str) -> TranscriptionRecord`:

1. `IngestionDatabase.get_video(video_id)` — raise if not found
2. `IngestionDatabase.list_video_files(video_id)` — find `VideoFileKind.VIDEO` path
3. Load `metadata.json` from disk
4. `TranscriptionDatabase.create_or_reset_transcription(video_id)` → PROCESSING
5. `GeminiTranscriber.transcribe(video_path, video_record, metadata)` → `TranscriptionPayload`
6. Assemble `RichVideoTranscription` — fill document-level fields from code:
   - `video_id`, `source_url`, `platform`, `title`, `creator_name`, `upload_date` ← `VideoRecord`
   - `total_duration` ← convert `VideoRecord.duration` seconds → MM:SS
   - `resolution`, `aspect_ratio` ← from `metadata.json`
   - `speakers`, `segments` ← from LLM payload
7. Save `transcription.json` to video directory
8. Update status to COMPLETED
9. On exception: FAILED + error_message + re-raise

---

## .env.example

```bash
# Google AI (Gemini) — required
GOOGLE_API_KEY=

# Gemini model — change to test different models
GEMINI_MODEL=gemini-3-flash-preview

# LangSmith tracing — set both to enable, leave empty to disable
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=creator-joy
```

Source with: `export $(grep -v '^#' .env | xargs)`

---

## requirements.txt Additions

```
langchain-google-genai>=4.0.0
google-genai>=1.50.0
langchain>=0.3.0
pydantic>=2.0.0
```

---

## End-to-End Test (dev_test_transcription.py)

1. Ingest a short video (or use existing video_id from prior ingestion)
2. `TranscriptionService.transcribe_video(video_id)`
3. Print: status, path, first 3 segments
4. Confirm `transcription.json` on disk and SQLite row = COMPLETED

---

## LangSmith Setup

1. Sign up at https://smith.langchain.com (free: 5,000 traces/month, 14-day retention)
2. Create API key: Settings → API Keys
3. Add to `.env`:
   ```
   LANGCHAIN_TRACING_V2=true
   LANGCHAIN_API_KEY=<your-key>
   LANGCHAIN_PROJECT=creator-joy
   ```
4. Source `.env` before running — all LangChain calls trace automatically, zero code changes

---

## After Implementation

Populate `plans/rich-video-transcription/implementation-notes.md` with:
- All files created/modified and what each does
- Call graph: test → service → transcriber + database → Gemini
- How to run the end-to-end test (activate venv, install requirements, source .env, run script)
- LangSmith setup steps
- How to change the Gemini model
- Where transcription.json ends up on disk
- How the JSON parsing fallback works and what to check if all 3 attempts fail
