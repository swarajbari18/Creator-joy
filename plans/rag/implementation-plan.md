# RAG Pipeline — Complete Implementation Plan

> **Audience:** This document is addressed to a blind implementation agent that has zero context
> of the conversations that produced it. Every decision is explained. Every pattern is shown.
> Every API gotcha is called out. Follow this document exactly; do not improvise.

---

## Part 1 — What Creator-Joy Is and Why This Matters

Creator-Joy is a video analytics chatbot for content creators. A creator uploads a YouTube URL,
the system downloads the video, runs a rich multimodal transcription through Gemini, and stores
the result as a detailed `transcription.json` file on disk. The transcription contains not just
words but frame-level production data: shot types, camera angles, lighting, on-screen text,
graphics, editing cuts, audio analysis, and more — one JSON object per ~10-second segment.

The RAG pipeline is the retrieval backbone. When a creator asks "show me all segments where I'm
using a lower-third", or "find segments where I sound most energetic", the system needs to search
across dozens of videos efficiently. This module builds that capability.

The three deliverables are:
1. **Qdrant indexing** — load transcription.json segments into a local Qdrant vector database
2. **search_segments()** — a single Python function serving three search modes
3. **skill.md** — a system-prompt-style document teaching an LLM agent how to use the search tool

---

## Part 2 — What Already Exists (Do Not Recreate)

### Module structure

```
backend/
  creator_joy/
    ingestion/
      __init__.py          ← exports VideoIngestionService, IngestionSettings
      models.py            ← VideoStatus, VideoFileKind, ProjectRecord, VideoRecord,
                              VideoFileRecord, IngestionSettings
      database.py          ← IngestionDatabase (projects, videos, video_files tables)
      downloader.py        ← yt-dlp wrapper
      service.py           ← VideoIngestionService
      logging_config.py    ← configure_debug_logging()
    transcription/
      __init__.py          ← exports TranscriptionService, TranscriptionSettings,
                              TranscriptionRecord, TranscriptionStatus
      models.py            ← TranscriptionStatus, TranscriptionRecord, TranscriptionSettings
      database.py          ← TranscriptionDatabase (transcriptions table)
      schema.py            ← Pydantic models for transcription.json
      transcriber.py       ← GeminiTranscriber
      service.py           ← TranscriptionService
  tests/
    dev_test_ingestion.py
    dev_test_transcription.py
  downloads/               ← all video files, metadata, transcription.json files live here
  requirements.txt
  .env.example
```

### SQLite database

Single file: `downloads/creator_joy.sqlite3`

Tables already in use:
- `projects (id, name, description, created_at, updated_at)`
- `videos (id, project_id, source_url, normalized_url, platform, yt_dlp_id, title, uploader,
   duration, upload_date, status, error_message, metadata_path, created_at, updated_at)`
- `video_files (id, video_id, kind, path, ext, size_bytes, created_at)`
- `transcriptions (id, video_id, status, transcription_path, error_message, gemini_model,
   created_at, updated_at)`

The `project_id` column lives in the `videos` table, **not** in `transcription.json`.
At index time, the ingestor must query `ingestion_db.get_video(video_id).project_id` to retrieve it.

### File layout on disk

```
downloads/
  projects/
    {project_id}/
      videos/
        {video_id}/
          source_video.mp4
          audio.mp3
          metadata.json        ← yt-dlp raw metadata
          transcription.json   ← rich video transcription (the source data for RAG)
  creator_joy.sqlite3
```

### Known video for testing

- project_id: `fdb0d91b-8e8e-4fe3-87ff-1fc4fc89ffde`
- video_id:   `c8604c66-2a5d-4ce4-96b8-43186fad1e46`
- transcription.json: `downloads/projects/fdb0d91b-.../videos/c8604c66-.../transcription.json`
- 12 segments, total duration 02:12, YouTube video about AI agents by Google Cloud

---

## Part 3 — The Transcription JSON Structure

Every field shown below exists in real data. The implementation must handle ALL of them.

### Document-level fields (top of JSON)

```json
{
  "video_id": "c8604c66-2a5d-4ce4-96b8-43186fad1e46",
  "source_url": "https://www.youtube.com/watch?v=d0wUM8hIaxE",
  "platform": "Youtube",
  "title": "AI agents explained (2-minute AI with Google)",
  "creator_name": "Google Cloud",
  "upload_date": "20260505",
  "total_duration": "02:12",
  "resolution": "1920x1080",
  "aspect_ratio": "1.78",
  "speakers": {
    "speaker_1": {
      "identified_name": "[unclear]",
      "identification_source": "visible speaker",
      "role": "Presenter"
    }
  },
  "segments": [...]
}
```

### Full segment example (segment 1)

```json
{
  "segment_id": 1,
  "timecode_start": "00:00",
  "timecode_end": "00:13",
  "duration_seconds": 13.0,
  "observable_summary": "A woman with long dark hair stands in a studio setting and introduces the concept of AI agents.",
  "speech": {
    "speaker_id": "speaker_1",
    "speaker_visible": true,
    "transcript": "What if your AI didn't just provide answers, but autonomously completed your to-do list? Meet the AI agent, a digital assistant that moves beyond chat to take direct action.",
    "language": "English"
  },
  "frame": {
    "shot_type": "MCU",
    "camera_angle": "eye-level",
    "camera_movement": "static",
    "subjects_in_frame": ["speaker_1"],
    "depth_of_field": "shallow"
  },
  "background": {
    "type": "studio",
    "description": "A modern studio with a wooden slat wall and a bookshelf.",
    "elements_visible": ["wooden slat wall", "bookshelf", "books", "plants"]
  },
  "lighting": {
    "key_light_direction": "front",
    "light_quality": "soft",
    "catch_light_in_eyes": true,
    "color_temperature_feel": "neutral",
    "notable": "Even, flattering lighting on the subject."
  },
  "on_screen_text": {
    "present": false,
    "entries": []
  },
  "graphics_and_animations": {
    "present": false,
    "entries": []
  },
  "editing": {
    "cut_event": {"occurred": false, "type": null},
    "transition_effect": "none",
    "speed_change": "none"
  },
  "audio": {
    "music": {
      "present": true,
      "tempo_feel": "medium",
      "genre_feel": "upbeat-pop",
      "volume_relative_to_speech": "background",
      "notable_change": "none"
    },
    "sound_effects": {"present": false, "entries": []},
    "ambient": "room-tone",
    "audio_quality": "clean-studio"
  },
  "production_observables": {
    "microphone_type_inferred": "lav",
    "props_in_use": [],
    "wardrobe_notable": "Dark grey t-shirt, blue jeans.",
    "color_grade_feel": "vibrant"
  }
}
```

All string fields can contain `[unclear]` or `[inaudible]` — do not treat them as errors.

---

## Part 4 — Codebase Patterns You Must Follow Exactly

Every new file must match the style of the existing codebase. Read this section carefully.

### Pattern 1: frozen dataclass for records and settings

```python
# models.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
import os

class IndexStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass(frozen=True)
class IndexRecord:
    id: str
    video_id: str
    project_id: str
    status: IndexStatus
    segments_indexed: int | None
    qdrant_collection: str
    error_message: str | None
    created_at: str
    updated_at: str
```

### Pattern 2: settings with env var defaults via field(default_factory=...)

```python
def _env_str(key: str, default: str) -> str:
    return os.environ.get(key, default)

def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    return int(val) if val else default

@dataclass(frozen=True)
class RAGSettings:
    storage_root: Path = field(default_factory=lambda: Path("downloads"))
    database_filename: str = "creator_joy.sqlite3"
    qdrant_host: str = field(default_factory=lambda: _env_str("QDRANT_HOST", "localhost"))
    qdrant_port: int = field(default_factory=lambda: _env_int("QDRANT_PORT", 6333))
    collection_name: str = "video_segments"
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    sparse_model: str = "Qdrant/minicoil-v1"
    reranker_model: str = "Qwen/Qwen3-Reranker-0.6B"
    embedding_dim: int = 4096
    use_gpu: bool = True
    use_contextual_prefix: bool = False
    prefetch_k: int = 50
    rerank_top_n: int = 10

    @property
    def database_path(self) -> Path:
        return self.storage_root / self.database_filename
```

### Pattern 3: database class with _connect(), _initialize(), create_or_reset_*

```python
# database.py
from __future__ import annotations
import logging, sqlite3, uuid
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

def utc_now() -> str:
    return datetime.now(UTC).isoformat()

class RAGDatabase:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        logger.debug("Initializing RAG database at %s", database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS rag_index (
                    id TEXT PRIMARY KEY,
                    video_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    segments_indexed INTEGER,
                    qdrant_collection TEXT NOT NULL,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
                );
            """)
```

### Pattern 4: service with try/except/FAILED status and post-insert validation

```python
# service.py
def index_video(self, video_id: str) -> IndexRecord:
    record = self.rag_db.create_or_reset_index(
        video_id=video_id,
        project_id=project_id,
        collection_name=self.settings.collection_name,
    )
    self.rag_db.update_index_status(record.id, IndexStatus.PROCESSING)
    try:
        segments_indexed = self.ingestor.index_video(video_id)
        self.rag_db.update_index_status(
            record.id,
            IndexStatus.COMPLETED,
            segments_indexed=segments_indexed,
        )
    except Exception as exc:
        logger.exception("Indexing failed video_id=%s", video_id)
        self.rag_db.update_index_status(record.id, IndexStatus.FAILED, error_message=str(exc))
        raise

    completed = self.rag_db.get_index(record.id)
    if completed is None:
        raise RuntimeError(f"Completed index row disappeared: {record.id}")
    return completed
```

### Pattern 5: test file structure

```python
"""
End-to-end RAG test.

Usage:
    cd backend
    export $(grep -v '^#' .env | xargs)
    python -m tests.dev_test_rag
"""
from __future__ import annotations
import sys
from pathlib import Path
from creator_joy.ingestion.logging_config import configure_debug_logging

# ── Configuration ────────────────────────────────────────────────────────────
VIDEO_ID: str | None = "c8604c66-2a5d-4ce4-96b8-43186fad1e46"
INGEST_URL: str | None = None
STORAGE_ROOT = Path(__file__).parent.parent / "downloads"

def _print_section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")

def main() -> None:
    configure_debug_logging()
    ...

if __name__ == "__main__":
    main()
```

---

## Part 5 — 2026 Tech Stack Decisions

### Why these specific versions

This is the definitive stack as of May 2026. Previous research docs may have named different
models — those are outdated. Use only what is listed here.

**Dense embeddings: `Qwen/Qwen3-Embedding-0.6B`**
- 4096-dimensional output (NOT 2048 — older docs were wrong)
- SentenceTransformer API: `model.encode(texts, prompt_name="query"/"document")`
- Full BF16: ~1.2 GB VRAM
- Apache 2.0 license, no trust_remote_code required
- Hugging Face: `sentence-transformers` library loads it natively

**Sparse embeddings: `Qdrant/minicoil-v1`**
- Replaces BM42 (which Qdrant now labels "experimental/legacy")
- fastembed API: `SparseTextEmbedding("Qdrant/minicoil-v1")` — NOT `TextEmbedding`
- `TextEmbedding` only handles dense models. `minicoil-v1` is registered in fastembed's
  sparse registry and must be loaded with `SparseTextEmbedding` (from `fastembed` package)
- Returns `SparseEmbedding` objects with `.indices` and `.values`
- Requires `Modifier.IDF` in collection's sparse vector config
- Installed via `qdrant-client[fastembed]`

**Reranker: `Qwen/Qwen3-Reranker-0.6B`**
- CrossEncoder API: `CrossEncoder("Qwen/Qwen3-Reranker-0.6B")`
- `model.predict([(query, doc), ...])` returns float scores
- Full BF16: ~1.2 GB VRAM
- Both models fit together on a 4GB GPU without quantization

**Qdrant: `qdrant-client==1.17.1`**
- `client.search()` was removed in 1.16.0 — do NOT use it
- Use `client.query_points()` for all semantic search
- Use `client.scroll()` for structural-only retrieval
- Named vector collections (multi-vector per point)

**No quantization needed.** Qwen3-Embedding-0.6B + Qwen3-Reranker-0.6B together use ~2.4 GB
VRAM in full BF16, well within a 4 GB GPU. Any bitsandbytes quantization approach should be
ignored — the models are small enough to not need it.

---

## Part 6 — Qdrant Collection Schema

### Why three vectors per segment?

Each segment is stored with **two dense vectors** and **one sparse vector**. They answer
different kinds of questions:

**`dense_transcript`** — embeds the spoken words + `observable_summary`. Use this when the
query is about *what the creator is saying*. Example: "find segments where the creator
explains what an AI agent does."

**`dense_production`** — embeds the output of `build_production_description()`, a natural
language sentence constructed from shot type, camera angle, lighting, color grade, music,
editing cuts, etc. Use this when the query is about *how the video looks or feels*. Example:
"find segments that feel cinematic" or "find wide shots with dramatic music."

Both dense vectors live on the same Qdrant point under different named slots. The `search_vector`
parameter in `search_segments()` lets the caller choose `"dense_transcript"`,
`"dense_production"`, or `"both"` (fused with RRF).

**`sparse_minicoil`** — a learned sparse model (miniCOIL via fastembed). This is the
*lexical* signal, not keyword filtering. It's smarter than BM25: the model learns which tokens
matter in context. It fires strongly when a query word literally appears in the text or when
close lexical variants do. Dense vectors alone can miss exact keyword matches due to embedding
space compression — sparse fills that gap.

In hybrid search all three run in parallel as Prefetch candidates, then get fused via RRF
(Reciprocal Rank Fusion):

```
sparse_minicoil  →  lexical/keyword signal on transcript  ┐
dense_transcript →  semantic match on speech content      ├── RRF fusion → final ranked list
dense_production →  semantic match on production style    ┘
```

A segment scores well if it's a strong match on *any* of the three signals. This is why hybrid
outperforms either pure sparse or pure dense alone.

**`sparse_minicoil` is NOT the same as a structural keyword filter.** Structural filters
(Part 12 — `_build_filter()`) hit Qdrant payload indexes directly and are exact/boolean.
Sparse is a ranked signal, not a gate.

---

### Create the collection

```python
from qdrant_client import QdrantClient
from qdrant_client import models

client = QdrantClient(host="localhost", port=6333)

client.create_collection(
    collection_name="video_segments",
    vectors_config={
        "dense_transcript": models.VectorParams(
            size=4096,
            distance=models.Distance.COSINE,
            hnsw_config=models.HnswConfigDiff(m=16, ef_construct=100),
        ),
        "dense_production": models.VectorParams(
            size=4096,
            distance=models.Distance.COSINE,
            hnsw_config=models.HnswConfigDiff(m=16, ef_construct=100),
        ),
    },
    sparse_vectors_config={
        "sparse_minicoil": models.SparseVectorParams(
            modifier=models.Modifier.IDF
        )
    },
)
```

### Create payload indexes (MUST be done BEFORE any upsert)

```python
# project_id — tenant index for HNSW co-location
client.create_payload_index(
    collection_name="video_segments",
    field_name="project_id",
    field_schema=models.KeywordIndexParams(
        type=models.KeywordIndexType.KEYWORD,
        is_tenant=True,
    ),
)

# video_id
client.create_payload_index(
    collection_name="video_segments",
    field_name="video_id",
    field_schema=models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD),
)

# Structural filter fields
client.create_payload_index("video_segments", "shot_type",
    models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD))
client.create_payload_index("video_segments", "camera_angle",
    models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD))
client.create_payload_index("video_segments", "camera_movement",
    models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD))
client.create_payload_index("video_segments", "depth_of_field",
    models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD))
client.create_payload_index("video_segments", "background_type",
    models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD))
client.create_payload_index("video_segments", "key_light_direction",
    models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD))
client.create_payload_index("video_segments", "light_quality",
    models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD))
client.create_payload_index("video_segments", "color_temperature_feel",
    models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD))
client.create_payload_index("video_segments", "music_genre_feel",
    models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD))
client.create_payload_index("video_segments", "music_tempo_feel",
    models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD))
client.create_payload_index("video_segments", "audio_quality",
    models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD))
client.create_payload_index("video_segments", "color_grade_feel",
    models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD))
client.create_payload_index("video_segments", "cut_occurred",
    models.BoolIndexParams(type=models.BoolIndexType.BOOL))
client.create_payload_index("video_segments", "music_present",
    models.BoolIndexParams(type=models.BoolIndexType.BOOL))
client.create_payload_index("video_segments", "on_screen_text_present",
    models.BoolIndexParams(type=models.BoolIndexType.BOOL))
client.create_payload_index("video_segments", "graphics_present",
    models.BoolIndexParams(type=models.BoolIndexType.BOOL))
client.create_payload_index("video_segments", "speaker_visible",
    models.BoolIndexParams(type=models.BoolIndexType.BOOL))
client.create_payload_index("video_segments", "timecode_start_seconds",
    models.FloatIndexParams(type=models.FloatIndexType.FLOAT))
client.create_payload_index("video_segments", "timecode_end_seconds",
    models.FloatIndexParams(type=models.FloatIndexType.FLOAT))
client.create_payload_index("video_segments", "duration_seconds",
    models.FloatIndexParams(type=models.FloatIndexType.FLOAT))
client.create_payload_index("video_segments", "language",
    models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD))
client.create_payload_index("video_segments", "speaker_id",
    models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD))
```

### The `ensure_collection()` function

Place this in `backend/creator_joy/rag/collection.py`. It checks for existence before creating:

```python
def ensure_collection(client: QdrantClient, collection_name: str, embedding_dim: int) -> None:
    """Create collection + all payload indexes if they don't exist yet."""
    existing = [c.name for c in client.get_collections().collections]
    if collection_name in existing:
        logger.debug("Collection %s already exists", collection_name)
        return
    logger.debug("Creating collection %s dim=%s", collection_name, embedding_dim)
    # ... create_collection call as above ...
    # ... all create_payload_index calls as above ...
    logger.debug("Collection %s created with all payload indexes", collection_name)
```

---

## Part 7 — Qdrant Payload Structure Per Point

Each segment becomes one Qdrant point. The payload must be flat (no nested dicts) so that
Qdrant's payload filters can operate on individual fields.

```python
payload = {
    # ── Identity ──────────────────────────────────────────────
    "project_id":            video.project_id,       # str — TENANT field
    "video_id":              seg.video_id,            # str
    "segment_id":            seg.segment_id,          # int
    "video_title":           transcription.title,     # str
    "creator_name":          transcription.creator_name,  # str
    "platform":              transcription.platform,  # str
    "upload_date":           transcription.upload_date,   # str

    # ── Timecode ──────────────────────────────────────────────
    "timecode_start":        seg.timecode_start,      # str "MM:SS"
    "timecode_end":          seg.timecode_end,         # str "MM:SS"
    "timecode_start_seconds": timecode_to_seconds(seg.timecode_start),  # float
    "timecode_end_seconds":  timecode_to_seconds(seg.timecode_end),     # float
    "duration_seconds":      seg.duration_seconds,    # float

    # ── Speech ────────────────────────────────────────────────
    "transcript":            seg.speech.transcript,   # str (verbatim, can be [inaudible])
    "speaker_id":            seg.speech.speaker_id,   # str
    "speaker_visible":       seg.speech.speaker_visible,  # bool
    "language":              seg.speech.language,     # str

    # ── Frame ─────────────────────────────────────────────────
    "shot_type":             seg.frame.shot_type,     # str
    "camera_angle":          seg.frame.camera_angle,  # str
    "camera_movement":       seg.frame.camera_movement,   # str
    "depth_of_field":        seg.frame.depth_of_field,    # str
    "subjects_in_frame":     seg.frame.subjects_in_frame, # list[str]

    # ── Background ────────────────────────────────────────────
    "background_type":       seg.background.type,     # str
    "background_description": seg.background.description,  # str
    "background_elements":   seg.background.elements_visible,  # list[str]

    # ── Lighting ──────────────────────────────────────────────
    "key_light_direction":   seg.lighting.key_light_direction,   # str
    "light_quality":         seg.lighting.light_quality,         # str
    "catch_light_in_eyes":   seg.lighting.catch_light_in_eyes,   # bool
    "color_temperature_feel": seg.lighting.color_temperature_feel,  # str

    # ── On-screen text ────────────────────────────────────────
    "on_screen_text_present": seg.on_screen_text.present,  # bool
    "on_screen_texts":       [e.text for e in seg.on_screen_text.entries],  # list[str]

    # ── Graphics ──────────────────────────────────────────────
    "graphics_present":      seg.graphics_and_animations.present,  # bool

    # ── Editing ───────────────────────────────────────────────
    "cut_occurred":          seg.editing.cut_event.occurred,   # bool
    "cut_type":              seg.editing.cut_event.type,       # str | None
    "transition_effect":     seg.editing.transition_effect,    # str
    "speed_change":          seg.editing.speed_change,         # str

    # ── Audio ─────────────────────────────────────────────────
    "music_present":         seg.audio.music.present,          # bool
    "music_tempo_feel":      seg.audio.music.tempo_feel,       # str
    "music_genre_feel":      seg.audio.music.genre_feel,       # str
    "audio_quality":         seg.audio.audio_quality,          # str

    # ── Production ────────────────────────────────────────────
    "microphone_type":       seg.production_observables.microphone_type_inferred,  # str
    "color_grade_feel":      seg.production_observables.color_grade_feel,          # str
    "wardrobe_notable":      seg.production_observables.wardrobe_notable,          # str
    "props_in_use":          seg.production_observables.props_in_use,              # list[str]

    # ── Retrieval ─────────────────────────────────────────────
    "observable_summary":    seg.observable_summary,  # str — factual one-liner from Gemini
    "production_description": build_production_description(seg),  # str — see Part 8
}
```

---

## Part 8 — Embedding Utilities

### timecode_to_seconds()

```python
def timecode_to_seconds(timecode: str) -> float:
    """Convert 'MM:SS' to float seconds."""
    parts = timecode.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return 0.0
```

### build_production_description()

Converts nested production fields into a natural language sentence for the `dense_production`
vector. This text is embedded, not the raw field values.

```python
def build_production_description(seg: VideoSegment) -> str:
    """
    Flatten production metadata into a natural language sentence
    for the dense_production embedding vector.
    """
    parts = []

    shot = seg.frame.shot_type
    angle = seg.frame.camera_angle
    movement = seg.frame.camera_movement
    if shot not in ("[unclear]", ""):
        parts.append(f"{shot} shot")
    if angle not in ("[unclear]", ""):
        parts.append(f"{angle} angle")
    if movement not in ("static", "[unclear]", ""):
        parts.append(f"{movement} camera movement")

    bg = seg.background.type
    if bg not in ("[unclear]", ""):
        parts.append(f"{bg} background")

    light = seg.lighting.light_quality
    light_dir = seg.lighting.key_light_direction
    if light not in ("[unclear]", ""):
        parts.append(f"{light} lighting from {light_dir}")

    grade = seg.production_observables.color_grade_feel
    if grade not in ("[unclear]", ""):
        parts.append(f"{grade} color grade")

    mic = seg.production_observables.microphone_type_inferred
    if mic not in ("[unclear]", ""):
        parts.append(f"{mic} microphone")

    if seg.audio.music.present:
        genre = seg.audio.music.genre_feel
        if genre not in ("[unclear]", "none", ""):
            parts.append(f"{genre} background music")

    if seg.editing.cut_event.occurred:
        cut_type = seg.editing.cut_event.type or "cut"
        parts.append(f"{cut_type} edit")

    if seg.on_screen_text.present:
        parts.append("on-screen text overlay")
    if seg.graphics_and_animations.present:
        parts.append("graphics/animations")

    if not parts:
        return seg.observable_summary

    return ". ".join(parts).capitalize() + "."
```

---

## Part 9 — Embedding Classes (embedder.py)

All model loading is lazy — models are only instantiated when first called, not at class
construction time. This avoids 1+ GB of GPU memory being allocated before any actual work.

### DenseEmbedder

```python
from sentence_transformers import SentenceTransformer
import numpy as np

class DenseEmbedder:
    def __init__(self, model_name: str, use_gpu: bool = True) -> None:
        self.model_name = model_name
        self.use_gpu = use_gpu
        self._model: SentenceTransformer | None = None

    def _load(self) -> SentenceTransformer:
        if self._model is None:
            device = "cuda" if self.use_gpu else "cpu"
            logger.debug("Loading dense embedding model %s on %s", self.model_name, device)
            self._model = SentenceTransformer(self.model_name, device=device)
        return self._model

    def encode_query(self, text: str) -> list[float]:
        model = self._load()
        vec = model.encode([text], prompt_name="query", normalize_embeddings=True)
        return vec[0].tolist()

    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vecs = model.encode(texts, prompt_name="document", normalize_embeddings=True,
                            batch_size=32, show_progress_bar=False)
        return [v.tolist() for v in vecs]
```

### SparseEmbedder

```python
from fastembed import SparseTextEmbedding, SparseEmbedding

class SparseEmbedder:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: SparseTextEmbedding | None = None

    def _load(self) -> SparseTextEmbedding:
        if self._model is None:
            logger.debug("Loading sparse embedding model %s", self.model_name)
            self._model = SparseTextEmbedding(self.model_name)
        return self._model

    def encode(self, texts: list[str]) -> list[SparseEmbedding]:
        return list(self._load().embed(texts))

    def encode_query(self, text: str) -> SparseEmbedding:
        return self.encode([text])[0]
```

Note: Use `SparseTextEmbedding`, NOT `TextEmbedding`. fastembed maintains two separate model
registries — `TextEmbedding` is for dense models only. `minicoil-v1` lives in the sparse
registry and will raise `ValueError` if you try to load it via `TextEmbedding` (even with
`model_type="sparse"` — that parameter does not reroute to the sparse registry).
Access the sparse vector data as `embedding.indices` and `embedding.values`.
When passing to Qdrant, use `models.SparseVector(indices=..., values=...)`.

---

## Part 10 — Reranker (reranker.py)

```python
from sentence_transformers import CrossEncoder

class CrossEncoderReranker:
    def __init__(self, model_name: str, use_gpu: bool = True) -> None:
        self.model_name = model_name
        self.use_gpu = use_gpu
        self._model: CrossEncoder | None = None

    def _load(self) -> CrossEncoder:
        if self._model is None:
            device = "cuda" if self.use_gpu else "cpu"
            logger.debug("Loading reranker model %s on %s", self.model_name, device)
            self._model = CrossEncoder(self.model_name, device=device)
        return self._model

    def rerank(self, query: str, candidates: list[dict], top_n: int) -> list[dict]:
        """
        candidates: list of payload dicts from Qdrant
        Returns top_n candidates sorted by descending reranker score.
        Each returned dict has an extra "_rerank_score" key.
        """
        model = self._load()
        # Use transcript as the document text for reranking
        pairs = [(query, c.get("transcript", "") + " " + c.get("observable_summary", ""))
                 for c in candidates]
        scores = model.predict(pairs)
        for i, candidate in enumerate(candidates):
            candidate["_rerank_score"] = float(scores[i])
        ranked = sorted(candidates, key=lambda x: x["_rerank_score"], reverse=True)
        return ranked[:top_n]
```

---

## Part 11 — The Ingestor (ingestor.py)

### Deterministic point ID

```python
import uuid

_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

def make_point_id(video_id: str, segment_id: int) -> str:
    """UUID5-based deterministic ID. Same video+segment always maps to same point."""
    return str(uuid.uuid5(_NAMESPACE, f"{video_id}:{segment_id}"))
```

This ensures upserts are idempotent — re-indexing the same video overwrites existing points.

### VideoIngestor class flow

```python
class VideoIngestor:
    def __init__(
        self,
        settings: RAGSettings,
        ingestion_db: IngestionDatabase,
        dense_embedder: DenseEmbedder,
        sparse_embedder: SparseEmbedder,
        qdrant_client: QdrantClient,
    ) -> None:
        ...

    def index_video(self, video_id: str) -> int:
        """
        Load transcription.json for video_id, embed all segments,
        upsert into Qdrant. Returns number of segments indexed.
        """
        video = self.ingestion_db.get_video(video_id)
        project_id = video.project_id

        # Find transcription.json via video_files table or path convention
        transcription_path = self._find_transcription_path(video_id)
        transcription = RichVideoTranscription.model_validate_json(
            transcription_path.read_text(encoding="utf-8")
        )

        points = []
        transcript_texts = []
        production_texts = []
        for seg in transcription.segments:
            transcript_texts.append(seg.speech.transcript + " " + seg.observable_summary)
            production_texts.append(build_production_description(seg))

        dense_t_vecs = self.dense_embedder.encode_documents(transcript_texts)
        dense_p_vecs = self.dense_embedder.encode_documents(production_texts)
        sparse_vecs = self.sparse_embedder.encode(transcript_texts)

        for i, seg in enumerate(transcription.segments):
            payload = _build_payload(seg, transcription, project_id)
            sparse = sparse_vecs[i]
            point = models.PointStruct(
                id=make_point_id(video_id, seg.segment_id),
                vector={
                    "dense_transcript": dense_t_vecs[i],
                    "dense_production": dense_p_vecs[i],
                    "sparse_minicoil": models.SparseVector(
                        indices=sparse.indices,
                        values=sparse.values,
                    ),
                },
                payload=payload,
            )
            points.append(point)

        self.qdrant_client.upsert(
            collection_name=self.settings.collection_name,
            points=points,
        )
        logger.debug("Indexed %s segments for video_id=%s", len(points), video_id)
        return len(points)

    def _find_transcription_path(self, video_id: str) -> Path:
        video_files = self.ingestion_db.list_video_files(video_id)
        # Check video_files table for a registered transcription.json
        # Fall back to path convention: downloads/projects/{pid}/videos/{vid}/transcription.json
        video = self.ingestion_db.get_video(video_id)
        conventional = (
            self.settings.storage_root
            / "projects"
            / video.project_id
            / "videos"
            / video_id
            / "transcription.json"
        )
        if conventional.exists():
            return conventional
        raise RuntimeError(
            f"transcription.json not found for video_id={video_id}. "
            "Run transcription first."
        )
```

---

## Part 12 — The Search Tool (retriever.py)

### Data models

```python
# In models.py

@dataclass
class StructuralFilters:
    """All None by default. Set only the fields you want to filter on."""
    # Keyword filters (exact match)
    shot_type: str | None = None
    camera_angle: str | None = None
    camera_movement: str | None = None
    depth_of_field: str | None = None
    background_type: str | None = None
    key_light_direction: str | None = None
    light_quality: str | None = None
    color_temperature_feel: str | None = None
    music_genre_feel: str | None = None
    music_tempo_feel: str | None = None
    audio_quality: str | None = None
    color_grade_feel: str | None = None
    language: str | None = None
    speaker_id: str | None = None
    cut_type: str | None = None

    # Boolean filters
    speaker_visible: bool | None = None
    music_present: bool | None = None
    on_screen_text_present: bool | None = None
    graphics_present: bool | None = None
    cut_occurred: bool | None = None
    catch_light_in_eyes: bool | None = None

    # Range filters
    duration_min_seconds: float | None = None
    duration_max_seconds: float | None = None
    timecode_start_min_seconds: float | None = None
    timecode_start_max_seconds: float | None = None

    # Multi-value filters (match ANY)
    video_ids: list[str] | None = None  # additional per-segment video filter


@dataclass(frozen=True)
class SegmentResult:
    point_id: str
    score: float
    video_id: str
    project_id: str
    segment_id: int
    timecode_start: str
    timecode_end: str
    transcript: str
    observable_summary: str
    shot_type: str
    payload: dict  # full payload for downstream use


@dataclass(frozen=True)
class SearchResult:
    mode: str          # "structural" | "semantic" | "hybrid"
    operation: str     # "FETCH" | "COUNT" | "SUM_duration" | "GROUP_BY"
    total_count: int
    segments: list[SegmentResult]
    group_by_data: dict | None  # populated when operation="GROUP_BY"

    def to_dict(self) -> dict:
        """LangChain tool compatibility."""
        return {
            "mode": self.mode,
            "operation": self.operation,
            "total_count": self.total_count,
            "segments": [
                {
                    "point_id": s.point_id,
                    "score": s.score,
                    "video_id": s.video_id,
                    "segment_id": s.segment_id,
                    "timecode_start": s.timecode_start,
                    "timecode_end": s.timecode_end,
                    "transcript": s.transcript,
                    "observable_summary": s.observable_summary,
                    "shot_type": s.shot_type,
                }
                for s in self.segments
            ],
            "group_by_data": self.group_by_data,
        }
```

### search_segments() — the main function

```python
from typing import Literal

def search_segments(
    # ── Mode 1: Structural ──────────────────────────────────────────────────
    filters: StructuralFilters | None = None,
    operation: Literal["FETCH", "COUNT", "SUM_duration", "GROUP_BY"] = "FETCH",
    group_by_field: str | None = None,
    # ── Mode 2 & 3: Semantic ────────────────────────────────────────────────
    nl_query: str | None = None,
    search_vector: Literal["dense_transcript", "dense_production", "both"] = "dense_transcript",
    top_k: int = 10,
    
    client: QdrantClient = ...,
    dense_embedder: DenseEmbedder = ...,
    sparse_embedder: SparseEmbedder = ...,
    reranker: CrossEncoderReranker = ...,
    settings: RAGSettings = ...,
    # ── Dependencies (injected by Langchain Tool Runtime. the agent never sees these args) ───────────────────────────────
    project_id: str,
    video_ids: list[str] | None = None,
) -> SearchResult:
    """
    Mode is inferred from arguments:
      nl_query=None, filters set  → Mode 1: structural (scroll + aggregation)
      nl_query set,  filters=None → Mode 2: pure semantic (hybrid BM + dense, then rerank)
      both set                    → Mode 3: hybrid (structural pre-filter, then semantic)
      both None                   → raises ValueError
    """
    if nl_query is None and filters is None:
        raise ValueError("At least one of nl_query or filters must be provided.")

    mode = (
        "structural" if nl_query is None
        else "semantic" if filters is None
        else "hybrid"
    )
    ...
```

### _build_filter() — converts StructuralFilters to Qdrant Filter

```python
from qdrant_client.models import Filter, FieldCondition, MatchValue, Range, MatchAny

def _build_filter(
    project_id: str,
    video_ids: list[str] | None,
    filters: StructuralFilters | None,
) -> Filter:
    must = [
        FieldCondition(key="project_id", match=MatchValue(value=project_id))
    ]

    if video_ids:
        must.append(FieldCondition(key="video_id", match=MatchAny(any=video_ids)))

    if filters is None:
        return Filter(must=must)

    keyword_fields = [
        "shot_type", "camera_angle", "camera_movement", "depth_of_field",
        "background_type", "key_light_direction", "light_quality",
        "color_temperature_feel", "music_genre_feel", "music_tempo_feel",
        "audio_quality", "color_grade_feel", "language", "speaker_id", "cut_type",
    ]
    for field in keyword_fields:
        val = getattr(filters, field, None)
        if val is not None:
            must.append(FieldCondition(key=field, match=MatchValue(value=val)))

    bool_fields = [
        "speaker_visible", "music_present", "on_screen_text_present",
        "graphics_present", "cut_occurred", "catch_light_in_eyes",
    ]
    for field in bool_fields:
        val = getattr(filters, field, None)
        if val is not None:
            must.append(FieldCondition(key=field, match=MatchValue(value=val)))

    if filters.duration_min_seconds is not None or filters.duration_max_seconds is not None:
        must.append(FieldCondition(
            key="duration_seconds",
            range=Range(
                gte=filters.duration_min_seconds,
                lte=filters.duration_max_seconds,
            ),
        ))

    if filters.timecode_start_min_seconds is not None or filters.timecode_start_max_seconds is not None:
        must.append(FieldCondition(
            key="timecode_start_seconds",
            range=Range(
                gte=filters.timecode_start_min_seconds,
                lte=filters.timecode_start_max_seconds,
            ),
        ))

    return Filter(must=must)
```

### Mode 1 — structural scroll

```python
def _structural_search(
    client: QdrantClient,
    collection_name: str,
    qdrant_filter: Filter,
    operation: str,
    group_by_field: str | None,
) -> SearchResult:

    if operation == "COUNT":
        count_result = client.count(
            collection_name=collection_name,
            count_filter=qdrant_filter,   # ← count_filter=
        )
        return SearchResult(
            mode="structural", operation="COUNT",
            total_count=count_result.count, segments=[], group_by_data=None,
        )

    # FETCH, SUM_duration, GROUP_BY — all need scroll
    all_records = []
    offset = None
    while True:
        records, next_offset = client.scroll(
            collection_name=collection_name,
            scroll_filter=qdrant_filter,   # ← scroll_filter= NOT filter=
            with_payload=True,
            limit=1000,
            offset=offset,
        )
        all_records.extend(records)
        if next_offset is None:
            break
        offset = next_offset

    if operation == "SUM_duration":
        total = sum(r.payload.get("duration_seconds", 0) for r in all_records)
        return SearchResult(
            mode="structural", operation="SUM_duration",
            total_count=int(total), segments=[], group_by_data={"sum_duration_seconds": total},
        )

    if operation == "GROUP_BY":
        if group_by_field is None:
            raise ValueError("group_by_field required for GROUP_BY operation")
        groups: dict[str, int] = {}
        for r in all_records:
            val = str(r.payload.get(group_by_field, "[missing]"))
            groups[val] = groups.get(val, 0) + 1
        return SearchResult(
            mode="structural", operation="GROUP_BY",
            total_count=len(all_records), segments=[],
            group_by_data={"field": group_by_field, "counts": groups},
        )

    # FETCH
    segments = [_record_to_segment_result(r, score=1.0) for r in all_records]
    return SearchResult(
        mode="structural", operation="FETCH",
        total_count=len(segments), segments=segments, group_by_data=None,
    )
```

### Mode 2 — pure semantic (hybrid BM + dense)

```python
def _semantic_search(
    client: QdrantClient,
    collection_name: str,
    nl_query: str,
    search_vector: str,
    project_id: str,
    qdrant_filter: Filter,
    top_k: int,
    prefetch_k: int,
    dense_embedder: DenseEmbedder,
    sparse_embedder: SparseEmbedder,
    reranker: CrossEncoderReranker,
    rerank_top_n: int,
) -> list[SegmentResult]:

    query_sparse = sparse_embedder.encode_query(nl_query)
    query_dense = dense_embedder.encode_query(nl_query)

    if search_vector == "both":
        # Two dense prefetches fused with RRF
        prefetch = [
            models.Prefetch(
                query=models.SparseVector(
                    indices=query_sparse.indices, values=query_sparse.values
                ),
                using="sparse_minicoil",
                filter=qdrant_filter,   # ← filter= inside Prefetch
                limit=prefetch_k,
            ),
            models.Prefetch(
                query=query_dense,
                using="dense_transcript",
                filter=qdrant_filter,
                limit=prefetch_k,
            ),
            models.Prefetch(
                query=query_dense,
                using="dense_production",
                filter=qdrant_filter,
                limit=prefetch_k,
            ),
        ]
    else:
        prefetch = [
            models.Prefetch(
                query=models.SparseVector(
                    indices=query_sparse.indices, values=query_sparse.values
                ),
                using="sparse_minicoil",
                filter=qdrant_filter,
                limit=prefetch_k,
            ),
            models.Prefetch(
                query=query_dense,
                using=search_vector,
                filter=qdrant_filter,
                limit=prefetch_k,
            ),
        ]

    results = client.query_points(
        collection_name=collection_name,
        prefetch=prefetch,
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        query_filter=qdrant_filter,     # ← query_filter= on query_points (NOT filter=)
        limit=top_k * 3,
        with_payload=True,
    )

    candidates = [r.payload for r in results.points]
    if nl_query and reranker and candidates:
        candidates = reranker.rerank(nl_query, candidates, top_n=rerank_top_n)

    segments = [_payload_to_segment_result(p, score=p.get("_rerank_score", 0.0))
                for p in candidates[:top_k]]
    return segments
```

### Mode 3 — hybrid

Mode 3 uses `_build_filter()` from the structural filters, then passes that filter into the
semantic search Prefetch objects. The filter narrows the candidate set before vector search runs.
This means `_semantic_search()` already handles Mode 3 — just pass the non-None `qdrant_filter`
with the structural conditions. No separate code path needed.

---

## Part 13 — RAGService (service.py)

```python
from qdrant_client import QdrantClient

class RAGService:
    def __init__(self, settings: RAGSettings | None = None) -> None:
        self.settings = settings or RAGSettings()
        logger.debug("Creating RAGService settings=%s", self.settings)
        self.settings.storage_root.mkdir(parents=True, exist_ok=True)

        self.ingestion_db = IngestionDatabase(self.settings.database_path)
        self.rag_db = RAGDatabase(self.settings.database_path)

        self.qdrant_client = QdrantClient(
            host=self.settings.qdrant_host,
            port=self.settings.qdrant_port,
        )
        ensure_collection(
            self.qdrant_client,
            self.settings.collection_name,
            self.settings.embedding_dim,
        )

        self.dense_embedder = DenseEmbedder(
            self.settings.embedding_model, self.settings.use_gpu
        )
        self.sparse_embedder = SparseEmbedder(self.settings.sparse_model)
        self.reranker = CrossEncoderReranker(
            self.settings.reranker_model, self.settings.use_gpu
        )
        self.ingestor = VideoIngestor(
            settings=self.settings,
            ingestion_db=self.ingestion_db,
            dense_embedder=self.dense_embedder,
            sparse_embedder=self.sparse_embedder,
            qdrant_client=self.qdrant_client,
        )

    def index_video(self, video_id: str) -> IndexRecord:
        video = self.ingestion_db.get_video(video_id)
        if video is None:
            raise ValueError(f"Video not found: {video_id}")

        record = self.rag_db.create_or_reset_index(
            video_id=video_id,
            project_id=video.project_id,
            collection_name=self.settings.collection_name,
        )
        self.rag_db.update_index_status(record.id, IndexStatus.PROCESSING)

        try:
            count = self.ingestor.index_video(video_id)
            self.rag_db.update_index_status(
                record.id, IndexStatus.COMPLETED, segments_indexed=count
            )
        except Exception as exc:
            logger.exception("RAG indexing failed video_id=%s", video_id)
            self.rag_db.update_index_status(record.id, IndexStatus.FAILED, error_message=str(exc))
            raise

        completed = self.rag_db.get_index(record.id)
        if completed is None:
            raise RuntimeError(f"Completed index row disappeared: {record.id}")
        return completed

    def search(
        self,
        project_id: str,
        video_ids: list[str] | None = None,
        filters: StructuralFilters | None = None,
        operation: str = "FETCH",
        group_by_field: str | None = None,
        nl_query: str | None = None,
        search_vector: str = "dense_transcript",
        top_k: int = 10,
    ) -> SearchResult:
        return search_segments(
            project_id=project_id,
            video_ids=video_ids,
            filters=filters,
            operation=operation,
            group_by_field=group_by_field,
            nl_query=nl_query,
            search_vector=search_vector,
            top_k=top_k,
            client=self.qdrant_client,
            dense_embedder=self.dense_embedder,
            sparse_embedder=self.sparse_embedder,
            reranker=self.reranker,
            settings=self.settings,
        )
```

---

## Part 14 — skill.md

### Location

`backend/creator_joy/skills/search_skill/skill.md`

Create the `backend/creator_joy/skills/` and `backend/creator_joy/skills/search_skill/`
directories. `skill.md` is the only file needed there.

### What skill.md is

This is NOT developer documentation. It is a system-prompt-style document addressed directly
to an LLM agent. It should read as a set of instructions given to the agent, not as a
description of an API. Use second person ("you should", "prefer", "never").

### Required content structure

**Section 1 — Philosophy**
You have access to a `search_segments` tool. This tool searches through video segments from
creator content. Always prefer structural search (Mode 1) over semantic search (Mode 2).
Structural search is deterministic, fast, and exact. Semantic search is approximate.
Use semantic only when the query genuinely cannot be expressed as field values.
When both structural constraints AND a semantic query exist, use Mode 3 (hybrid).

**Section 2 — The Three Modes**

Mode 1 — Structural:
- Set `filters` with one or more `StructuralFilters` fields
- Set `nl_query=None`
- Set `operation` to FETCH, COUNT, SUM_duration, or GROUP_BY
- Use this for: "how many segments have lower-thirds?", "list all MCU shots",
  "total screen time with music", "group by shot type"

Mode 2 — Semantic:
- Set `nl_query` to the natural language query
- Leave `filters=None`
- Use only when the query cannot be expressed as field values
- "Find segments where the creator seems confident"
- "Show segments that feel cinematic"

Mode 3 — Hybrid:
- Set both `filters` and `nl_query`
- Structural filters narrow the candidate set first, then semantic search runs on that subset
- "Find wide shots where the creator is talking about growth" (shot_type=WS + nl_query)

**Section 3 — Operations Reference**

| operation    | what it returns                                      |
|--------------|------------------------------------------------------|
| FETCH        | list of matching segments with full payload          |
| COUNT        | integer count of matching segments                   |
| SUM_duration | total seconds of matching segment runtime            |
| GROUP_BY     | breakdown dict: field_value → count of segments      |

**Section 4 — Field Reference Table**

Full table of every filterable field, its type, and example values:

| field                   | type    | example values                                              |
|-------------------------|---------|-------------------------------------------------------------|
| shot_type               | keyword | ECU, CU, MCU, MS, MWS, WS, EWS, OTS, B-roll, Screen-recording |
| camera_angle            | keyword | eye-level, high-angle, low-angle, dutch                     |
| camera_movement         | keyword | static, pan-left, pan-right, dolly-in, handheld, gimbal     |
| depth_of_field          | keyword | shallow, deep                                               |
| background_type         | keyword | plain-wall, bookshelf, home-office, outdoor, studio, green-screen, blurred |
| key_light_direction     | keyword | left, right, front, above                                   |
| light_quality           | keyword | soft, hard, mixed                                           |
| color_temperature_feel  | keyword | warm, cool, neutral, mixed                                  |
| music_genre_feel        | keyword | lo-fi, electronic, cinematic, upbeat-pop, ambient, dramatic |
| music_tempo_feel        | keyword | slow, medium, fast                                          |
| audio_quality           | keyword | clean-studio, light-room-echo, heavy-reverb, background-noise |
| color_grade_feel        | keyword | warm, cool, neutral, high-contrast, desaturated, vibrant    |
| language                | keyword | English, Spanish, French, etc.                              |
| speaker_id              | keyword | speaker_1, speaker_2, etc.                                  |
| cut_type                | keyword | hard-cut, jump-cut, match-cut, J-cut, L-cut, smash-cut, dissolve |
| speaker_visible         | bool    | true / false                                                |
| music_present           | bool    | true / false                                                |
| on_screen_text_present  | bool    | true / false                                                |
| graphics_present        | bool    | true / false                                                |
| cut_occurred            | bool    | true / false                                                |
| duration_min_seconds    | float   | e.g. 5.0 to find segments ≥ 5 seconds                      |
| duration_max_seconds    | float   | e.g. 10.0 to find segments ≤ 10 seconds                    |
| timecode_start_min_seconds | float | e.g. 60.0 to find segments starting after 1:00             |
| timecode_start_max_seconds | float | e.g. 120.0 to find segments starting before 2:00           |

**Section 5 — 15 Worked Examples**

Cover all 3 modes and all 4 operations. Examples must be realistic creator analytics questions.

Example 1: "How many segments use a lower-third graphic?"
→ Mode 1, COUNT, filters: graphics_present=True

Example 2: "What shot types does this creator use most?"
→ Mode 1, GROUP_BY, group_by_field="shot_type"

Example 3: "Total screen time where music is playing"
→ Mode 1, SUM_duration, filters: music_present=True

Example 4: "Show all wide shots"
→ Mode 1, FETCH, filters: shot_type="WS"

Example 5: "Find segments with on-screen text in the first minute"
→ Mode 1, FETCH, filters: on_screen_text_present=True, timecode_start_max_seconds=60.0

Example 6: "What's the breakdown of background types across this video?"
→ Mode 1, GROUP_BY, group_by_field="background_type"

Example 7: "How much total time does speaker_1 appear on screen?"
→ Mode 1, SUM_duration, filters: speaker_id="speaker_1", speaker_visible=True

Example 8: "Show all segments with hard cuts"
→ Mode 1, FETCH, filters: cut_type="hard-cut"

Example 9: "Find segments where the creator sounds excited or energetic"
→ Mode 2 (nl_query only — cannot express emotion as field value)

Example 10: "Find segments that feel most cinematic"
→ Mode 2, search_vector="dense_production"

Example 11: "What does the creator say about AI agents?"
→ Mode 2, search_vector="dense_transcript"

Example 12: "Find wide shots where the creator is explaining a concept"
→ Mode 3, filters: shot_type="WS", nl_query="creator explaining concept"

Example 13: "Find segments with studio background where music is upbeat and the creator talks about growth"
→ Mode 3, filters: background_type="studio" + music_genre_feel="upbeat-pop", nl_query="growth"

Example 14: "Find segments with on-screen text after the 1-minute mark that relate to key takeaways"
→ Mode 3, filters: on_screen_text_present=True + timecode_start_min_seconds=60.0, nl_query="key takeaways"

Example 15: "Never use semantic search to find shot_type=MCU — that's a structural query."
→ Example of what NOT to do. Shot type is always structural.

**Section 6 — Common Mistakes to Avoid**

- Never use semantic search to find things expressible as field values (shot types, camera angles,
  boolean flags, etc.)
- Always scope to project_id. Never call search without project_id.
- GROUP_BY returns counts per field value, not segment lists. Use FETCH if you need the segments.
- SUM_duration returns total seconds, not a list. Convert to MM:SS if needed.
- COUNT is faster than FETCH followed by len() — prefer COUNT when you only need the number.

---

## Part 15 — End-to-End Test (dev_test_rag.py)

### Location

`backend/tests/dev_test_rag.py`

### What it must test (6 scenarios, all real data)

1. **Index the video** — call `service.index_video(video_id)`, confirm COMPLETED in SQLite,
   confirm `segments_indexed > 0`, confirm points exist in Qdrant via `client.count()`

2. **Mode 1 FETCH** — `filters=StructuralFilters(shot_type="MCU")`, confirm returned segments
   all have `shot_type="MCU"` in payload

3. **Mode 1 COUNT** — `filters=StructuralFilters(music_present=True)`, operation="COUNT",
   print the count

4. **Mode 1 GROUP_BY** — operation="GROUP_BY", group_by_field="shot_type", print breakdown

5. **Mode 2 semantic** — `nl_query="creator explaining what an AI agent does"`, print top 3
   results with timecodes and transcript snippets

6. **Mode 3 hybrid** — `filters=StructuralFilters(speaker_visible=True)` + `nl_query="AI agent"`,
   print top 3 results

### Required file structure

Follow the `dev_test_transcription.py` pattern exactly:
- Module docstring with Usage block
- `VIDEO_ID` / `INGEST_URL` / `STORAGE_ROOT` configuration block at top
- `_print_section()` helper
- `main()` function
- `if __name__ == "__main__": main()`
- `configure_debug_logging()` as the very first call in `main()`

### How to run

```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
export $(grep -v '^#' .env | xargs)
# Ensure Qdrant is running: docker run -p 6333:6333 qdrant/qdrant:v1.17.1
python -m tests.dev_test_rag
```

---

## Part 16 — Updated requirements.txt

Replace `backend/requirements.txt` with:

```
yt-dlp[default,curl-cffi]>=2025.0.0
langchain>=0.3.0
langchain-google-genai>=4.0.0
google-genai>=1.50.0
pydantic>=2.0.0
qdrant-client[fastembed]==1.17.1
sentence-transformers==5.4.1
fastembed==0.8.0
torch>=2.2.0
numpy>=1.26.0
```

---

## Part 17 — Updated .env.example

Add to the existing `.env.example`:

```bash
# ── Qdrant ────────────────────────────────────────────────────────────────────
# Local Qdrant instance (start with: docker run -p 6333:6333 qdrant/qdrant:v1.17.1)
QDRANT_HOST=localhost
QDRANT_PORT=6333
```

---

## Part 18 — __init__.py exports

`backend/creator_joy/rag/__init__.py`:

```python
from creator_joy.rag.models import (
    IndexRecord,
    IndexStatus,
    RAGSettings,
    SearchResult,
    SegmentResult,
    StructuralFilters,
)
from creator_joy.rag.service import RAGService
from creator_joy.rag.retriever import search_segments

__all__ = [
    "RAGService",
    "RAGSettings",
    "IndexRecord",
    "IndexStatus",
    "SearchResult",
    "SegmentResult",
    "StructuralFilters",
    "search_segments",
]
```

---

## Part 19 — Implementation Order

Implement in this exact order. Each step is independently testable.

1. `backend/creator_joy/rag/models.py` — all dataclasses and enums
2. `backend/creator_joy/rag/database.py` — RAGDatabase with rag_index table
3. `backend/creator_joy/rag/collection.py` — ensure_collection() with all payload indexes
4. `backend/creator_joy/rag/embedder.py` — DenseEmbedder, SparseEmbedder, utilities
5. `backend/creator_joy/rag/reranker.py` — CrossEncoderReranker
6. `backend/creator_joy/rag/ingestor.py` — VideoIngestor
7. `backend/creator_joy/rag/retriever.py` — search_segments(), _build_filter(), mode handlers
8. `backend/creator_joy/rag/service.py` — RAGService (wires everything together)
9. `backend/creator_joy/rag/__init__.py` — exports
10. `backend/creator_joy/skills/search_skill/skill.md` — system prompt document
11. `backend/tests/dev_test_rag.py` — end-to-end test
12. Update `backend/requirements.txt` and `backend/.env.example`

---

## Part 20 — Critical Implementation Warnings

**Warning 1: query_filter= vs scroll_filter= vs filter=**
This is the most important API gotcha. Using the wrong parameter name causes the filter to be
silently ignored — you get back all records instead of filtered results.

```python
# CORRECT
client.query_points(..., query_filter=qdrant_filter)   # ← query_filter= on query_points()
client.scroll(..., scroll_filter=qdrant_filter)         # ← scroll_filter= on scroll()
client.count(..., count_filter=qdrant_filter)           # ← count_filter= on count()
# Inside Prefetch objects:
models.Prefetch(..., filter=qdrant_filter)              # ← filter= inside Prefetch

# WRONG — silently ignored
client.query_points(..., filter=qdrant_filter)          # ← WRONG
client.scroll(..., filter=qdrant_filter)                # ← WRONG
```

**Warning 2: client.search() does not exist in qdrant-client 1.17.1**
It was removed in 1.16.0. Only `client.query_points()` for semantic, `client.scroll()` for
structural. Any code using `client.search()` will crash at runtime.

**Warning 3: Payload indexes must be created BEFORE upsert**
If you upsert first and create indexes after, existing points are NOT indexed. The index only
applies to points inserted after it was created. Always call `ensure_collection()` first.

**Warning 4: SparseEmbedding object access**
fastembed returns `SparseEmbedding` objects. Access as `embedding.indices` and `embedding.values`,
not `embedding["indices"]`. Wrap them in `models.SparseVector(indices=..., values=...)` for Qdrant.

**Warning 5: Qwen3 embedding dimensions**
Qwen3-Embedding-0.6B outputs 4096-dimensional vectors. The Qdrant collection MUST be created with
`size=4096`. Any other value (1024, 2048, 3072) will cause upsert failures.

**Warning 6: prompt_name for Qwen3**
```python
# For queries (user input):
model.encode([text], prompt_name="query")
# For documents (segments being indexed):
model.encode([text], prompt_name="document")
```
Using the wrong prompt_name degrades retrieval quality.

**Warning 7: frozen dataclass for StructuralFilters**
`StructuralFilters` should be a REGULAR (not frozen) dataclass with `None` defaults. Frozen
dataclasses cannot be partially initialized by setting fields after construction. The caller
needs to be able to create one and set specific fields.

**Warning 8: project_id must be in EVERY Qdrant query**
Every call to `query_points()`, `scroll()`, and `count()` must include a project_id filter.
Never retrieve results without scoping to project_id. This is a multi-tenant database.

**Warning 9: Scroll pagination**
`client.scroll()` returns `(records, next_offset)`. When `next_offset is None`, pagination is
complete. Always implement the while-loop pagination pattern — a single scroll call only returns
`limit` records (default 10, max 10000 per call).

**Warning 10: is_tenant=True must be on project_id ONLY**
Setting `is_tenant=True` on other fields causes performance regressions. Only `project_id` gets
this flag.

**Warning 11: miniCOIL, NOT BM42**
BM42 (`Qdrant/bm42-all-minilm-l6-v2-attentions`) is labeled "experimental/legacy" by Qdrant as
of 2026. Use `Qdrant/minicoil-v1`. The fastembed API is identical; only the model name changes.

**Warning 12: Use SparseTextEmbedding, not TextEmbedding, for sparse models**
```python
# CORRECT
from fastembed import SparseTextEmbedding
SparseTextEmbedding("Qdrant/minicoil-v1")

# WRONG — TextEmbedding only covers the dense model registry.
# minicoil-v1 is in the sparse registry. This raises ValueError at runtime,
# even with model_type="sparse" — that parameter does not reroute to SparseTextEmbedding.
TextEmbedding("Qdrant/minicoil-v1", model_type="sparse")
```

**Warning 13: transcription.json has no project_id**
The `transcription.json` file on disk does not contain `project_id`. You MUST query SQLite:
`ingestion_db.get_video(video_id).project_id` to get it at index time. Then store it in the
Qdrant payload so every retrieved point has it.

---

## Part 21 — What Was Rejected and Why

**Rejected: NVIDIA/llama-nemotron models**
No bitsandbytes INT8 quantization support for custom `trust_remote_code` models. The reranker
GGUF requires a non-standard llama.cpp fork. Too much complexity for marginal quality gain.
Replaced by Qwen3 0.6B stack which fits in 4GB VRAM without any quantization.

**Rejected: BM42**
Officially labeled "experimental" by Qdrant. Superseded by miniCOIL. Same fastembed API, just
a different model name.

**Rejected: Three separate search functions**
One unified `search_segments()` whose mode is inferred from which arguments are provided.
Cleaner API for the LLM tool, easier to maintain.

**Rejected: langchain-qdrant for search**
The langchain-qdrant abstraction hides the query_filter= vs filter= distinction and the prefetch
API. Direct qdrant-client gives full control with no surprises.

**Rejected: pytest with mocks**
No mocks. The test must hit a real local Qdrant instance and embed with real models. This is a
real end-to-end test following the `dev_test_transcription.py` pattern.

**Rejected: contextual prefix generation**
`use_contextual_prefix=False` by default. The Gemini-generated contextual prefix approach
(where each chunk gets a document-level summary prepended before embedding) is deferred.
The setting exists in `RAGSettings` but the ingestor must ignore it when False.

---

## Appendix — Directory Structure After Implementation

```
backend/
  creator_joy/
    rag/
      __init__.py       ← exports
      models.py         ← IndexStatus, IndexRecord, RAGSettings, StructuralFilters,
                           SegmentResult, SearchResult
      database.py       ← RAGDatabase (rag_index table)
      collection.py     ← ensure_collection()
      embedder.py       ← DenseEmbedder, SparseEmbedder, build_production_description(),
                           timecode_to_seconds()
      reranker.py       ← CrossEncoderReranker
      ingestor.py       ← VideoIngestor, make_point_id()
      retriever.py      ← search_segments(), _build_filter(), _structural_search(),
                           _semantic_search()
      service.py        ← RAGService
    skills/
      search_skill/
        skill.md        ← system prompt for LLM agent
  tests/
    dev_test_rag.py
  requirements.txt      ← updated
  .env.example          ← updated
```

---

*End of implementation plan. All decisions are final. Implement in the order specified in Part 19.*
