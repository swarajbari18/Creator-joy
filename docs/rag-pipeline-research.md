# Creator-Joy RAG Pipeline: Full Research Document

> Complete research synthesis from multi-agent investigation (Wave 1 + Wave 2 synthesis).
> Every finding, decision, tradeoff, and warning is recorded here. Nothing omitted.
> GPU context: 4GB VRAM available. All local models run on GPU.

---

## Table of Contents

1. [RAG Philosophy](#1-rag-philosophy)
2. [Data Architecture](#2-data-architecture)
3. [Final Tech Stack](#3-final-tech-stack)
4. [Model Details and Specs](#4-model-details-and-specs)
5. [Pipeline Architecture Overview](#5-pipeline-architecture-overview)
6. [Dense Embedding Strategy](#6-dense-embedding-strategy)
7. [Sparse BM42 Strategy](#7-sparse-bm42-strategy)
8. [Qdrant Collection Schema](#8-qdrant-collection-schema)
9. [Ingestion Pipeline](#9-ingestion-pipeline)
10. [Hybrid Search and Fusion](#10-hybrid-search-and-fusion)
11. [Reranking](#11-reranking)
12. [Query Routing: The Four Paths](#12-query-routing-the-four-paths)
13. [Agent Tool Design and Query Object Schema](#13-agent-tool-design-and-query-object-schema)
14. [Cross-Video Comparison Pattern](#14-cross-video-comparison-pattern)
15. [Neighbor Retrieval (Context Expansion)](#15-neighbor-retrieval-context-expansion)
16. [Contextual Prefix Generation](#16-contextual-prefix-generation)
17. [MMR Diversification](#17-mmr-diversification)
18. [Creator Query Taxonomy](#18-creator-query-taxonomy)
19. [What Works vs What Is Hype](#19-what-works-vs-what-is-hype)
20. [Key Implementation Warnings](#20-key-implementation-warnings)
21. [Build Priority Order](#21-build-priority-order)
22. [NVIDIA Model Alternatives Considered](#22-nvidia-model-alternatives-considered)

---

## 1. RAG Philosophy

RAG is not synonymous with semantic search and vector databases. Any system that helps a model query and retrieve appropriate context before generating something is a RAG system. A grep search is a RAG system. A SQL query is a RAG system.

This distinction matters for this product because our data is structured. We are not fighting the typical RAG problem of extracting meaning from unstructured PDFs or web pages. Our segments are clean, labeled, timestamped JSON with precise field values. A large fraction of creator questions are answerable by deterministic field-level lookups — and we should exploit that fully before reaching for semantic search.

### The Hybrid Approach

We use three distinct retrieval mechanisms in sequence, not the traditional "BM25 + semantic" hybrid:

1. **Metadata pre-filtering** — deterministic, zero embedding cost, maximum precision. Filters the candidate set using exact field values before any vector operations run.
2. **Hybrid sparse + dense search** — BM42 sparse (keyword-weighted by attention) + dense (semantic embedding) fused by RRF over the filtered set.
3. **Cross-encoder reranking** — expensive, highest precision, applied to the surviving top candidates.

This is a four-layer pipeline (pre-filter → hybrid search → MMR → rerank), not a two-layer one.

### What the Product Is

Creators upload one or more video URLs to a project. We transcribe each video into the rich segment schema. The creator then chats across all videos in that project. A single chat session can span multiple videos. The agent must determine, per query, whether it should target one specific video, a subset of videos, or all videos in the project.

The product sits at the intersection of competitor analysis and self-analysis. Creators want to understand:
- Why a video performed or underperformed
- What a competitor is doing differently at the production level
- How to improve a specific aspect (hook, pacing, production quality, CTAs)

These are product questions first and retrieval architecture questions second.

---

## 2. Data Architecture

Each video is transcribed into a structured JSON document with two levels:

### Document Level (one per video)

```json
{
  "video_id": "unique_identifier",
  "source_url": "original URL",
  "platform": "youtube | tiktok | instagram | linkedin | other",
  "title": "video title as shown",
  "creator_name": "channel/handle name",
  "upload_date": "YYYY-MM-DD",
  "total_duration": "MM:SS",
  "resolution": "1080p | 720p | 4K | vertical | etc",
  "aspect_ratio": "16:9 | 9:16 | 1:1 | 4:3",
  "speakers": {
    "Speaker_A": {
      "identified_name": "Name or [unclear]",
      "identification_source": "text-overlay | verbal-introduction | [inferred]",
      "role": "host | guest | interviewer | subject | [unclear]"
    }
  },
  "segments": [ ... ]
}
```

### Segment Level (one per observable event or change)

A new segment begins whenever anything meaningfully changes — a cut, a speaker change, a new overlay appearing, a camera movement, music shift. Not fixed time intervals. Each segment is self-contained and meaningful in isolation.

Full segment schema:

```json
{
  "segment_id": 1,
  "timecode_start": "MM:SS",
  "timecode_end": "MM:SS",
  "duration_seconds": 0,

  "speech": {
    "speaker_id": "Speaker_A | Speaker_B | Voiceover | [no speech]",
    "speaker_visible": true,
    "transcript": "exact verbatim words including um, uh, false starts",
    "language": "en | hi | es | [unclear]"
  },

  "frame": {
    "shot_type": "ECU | CU | MCU | MS | MWS | WS | EWS | OTS | POV | Two-shot | Insert | B-roll | Screen-recording | [unclear]",
    "camera_angle": "eye-level | high-angle | low-angle | dutch | [unclear]",
    "camera_movement": "static | pan-left | pan-right | tilt-up | tilt-down | dolly-in | dolly-out | handheld | gimbal | zoom-in | zoom-out | rack-focus | [unclear]",
    "subjects_in_frame": ["person", "laptop", "whiteboard"],
    "depth_of_field": "shallow | deep | [unclear]"
  },

  "background": {
    "type": "plain-wall | bookshelf | home-office | outdoor | studio | green-screen | blurred | [unclear]",
    "description": "brief factual description of what is visible behind the subject",
    "elements_visible": ["bookshelf", "plant", "monitor", "branded backdrop"]
  },

  "lighting": {
    "key_light_direction": "left | right | front | above | [unclear]",
    "light_quality": "soft | hard | mixed | [unclear]",
    "catch_light_in_eyes": true,
    "color_temperature_feel": "warm | cool | neutral | mixed | [unclear]",
    "notable": "ring light visible in catchlight | window light | neon accent | [none]"
  },

  "on_screen_text": {
    "present": true,
    "entries": [
      {
        "text": "exact text as it appears on screen",
        "position": "top-left | top-center | top-right | center | bottom-left | bottom-center | bottom-right",
        "style": "bold | italic | uppercase | lowercase | mixed",
        "color": "white | black | red | yellow | [describe]",
        "animation": "static | types-in | slides-in | fades-in | pops-in | [unclear]",
        "duration_on_screen_seconds": 0
      }
    ]
  },

  "graphics_and_animations": {
    "present": true,
    "entries": [
      {
        "type": "lower-third | counter | progress-bar | arrow | circle | logo | chart | meme | reaction-image | b-roll-overlay | [describe]",
        "description": "factual description of what the graphic is and where it appears",
        "position": "top-left | top-center | etc",
        "duration_seconds": 0
      }
    ]
  },

  "editing": {
    "cut_event": {
      "occurred": true,
      "type": "hard-cut | jump-cut | match-cut | J-cut | L-cut | smash-cut | dissolve | wipe | [unclear]"
    },
    "transition_effect": "none | whoosh | zoom-blur | spin | [describe] | [unclear]",
    "speed_change": "none | speed-ramp-up | speed-ramp-down | freeze-frame | [unclear]"
  },

  "audio": {
    "music": {
      "present": true,
      "tempo_feel": "slow | medium | fast | [unclear]",
      "genre_feel": "lo-fi | electronic | cinematic | upbeat-pop | ambient | dramatic | none | [unclear]",
      "volume_relative_to_speech": "background | equal | louder | no-speech | [unclear]",
      "notable_change": "drops | swells | cuts-out | new-track-starts | [none]"
    },
    "sound_effects": {
      "present": false,
      "entries": [
        {
          "type": "whoosh | ding | notification | impact | record-scratch | applause | [describe]",
          "timecode": "MM:SS"
        }
      ]
    },
    "ambient": "room-tone | outdoor | crowd | silence | [describe]",
    "audio_quality": "clean-studio | light-room-echo | heavy-reverb | background-noise | [unclear]"
  },

  "production_observables": {
    "microphone_type_inferred": "lav | shotgun | dynamic-desk | condenser | built-in | [unclear]",
    "props_in_use": ["list any props"],
    "wardrobe_notable": "casual | professional | branded | [describe] | [none noted]",
    "color_grade_feel": "warm | cool | neutral | high-contrast | desaturated | vibrant | [unclear]"
  }
}
```

### Schema Design Principles

- **Event-driven segmentation**: New segment on any meaningful change. Not fixed intervals.
- **Self-contained chunks**: Every segment understandable without surrounding context.
- **Observable language only**: No analysis baked in. The chatbot analyzes; the transcription records.
- **Exact over approximate**: Verbatim transcripts, specific shot type enums, exact overlay text.
- **Uncertainty over invention**: Unclear values use `[unclear]` or `[inaudible]`, never fabricated.

---

## 3. Final Tech Stack

| Component | Choice | Notes |
|---|---|---|
| **Vector DB** | Qdrant (local, self-hosted) | Native named vectors, filterable HNSW, BM42 sparse, hybrid search with RRF/DBSF fusion |
| **Dense embedding** | `nvidia/llama-nemotron-embed-1b-v2` | 1B params, ~2GB VRAM (BF16), fits on 4GB GPU, commercial license (NVIDIA Open Model License + Llama 3.2), Matryoshka dims (384/512/768/1024/2048), 8192 token context |
| **Sparse / BM42** | Qdrant FastEmbed `Qdrant/bm42-all-minilm-l6-v2-attentions` | Better than BM25 for short RAG chunks; replaces TF with transformer attention weights |
| **Reranking** | `nvidia/llama-nemotron-rerank-1b-v2` | 1B params, ~2GB VRAM (BF16), fits on 4GB GPU, commercial license, cross-encoder architecture |
| **GPU memory note** | Embed (~2GB) + Rerank (~2GB) = ~4GB total | Run sequentially (embed all at ingestion, rerank at query time); do NOT load both simultaneously unless quantized |
| **Fallback embedding** | `BAAI/bge-m3` (2.3GB, CPU or GPU) | If NVIDIA embed underperforms on our short structured text |
| **Fallback reranking** | `BAAI/bge-reranker-v2-m3` (1.1GB) | If NVIDIA reranker is problematic; Apache 2.0 |
| **Orchestration** | LangChain + Qdrant Python client directly | LangChain for chain/LLM/prompt logic; raw Qdrant client for search calls (fusion param control) |
| **Paid API** | Gemini only | Video transcription + contextual prefix generation at ingestion |
| **Framework** | LangChain with `langchain-qdrant` package | Native hybrid search support via `RetrievalMode.HYBRID` |

---

## 4. Model Details and Specs

### 4.1 NVIDIA Embedding Model: llama-nemotron-embed-1b-v2

- **HuggingFace**: `nvidia/llama-nemotron-embed-1b-v2`
- **Base model**: Llama-3.2-1B
- **Parameters**: 1 billion
- **Precision**: BF16
- **Disk size**: ~2 GB
- **VRAM required**: ~2–4 GB (GPU, BF16)
- **Embedding dimension**: 2048 (Matryoshka: 384 / 512 / 768 / 1024 / 2048)
- **Max context**: 8,192 tokens
- **Benchmark (BEIR+TechQA Recall@5)**: 68.60% at dim 2048, 64.48% at dim 384
- **License**: NVIDIA Open Model License + Llama 3.2 — **commercial use allowed**
- **Separate encode_query / encode_document methods**: yes, uses asymmetric encoding

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer(
    "nvidia/llama-nemotron-embed-1b-v2",
    trust_remote_code=True
)

query_embeddings = model.encode_query(["your query"], convert_to_tensor=True)
doc_embeddings = model.encode_document(["your video transcript chunk"], convert_to_tensor=True)
scores = model.similarity(query_embeddings, doc_embeddings)
```

### 4.2 NVIDIA Reranking Model: llama-nemotron-rerank-1b-v2

- **HuggingFace**: `nvidia/llama-nemotron-rerank-1b-v2`
- **Base model**: Llama-3.2-1B
- **Architecture**: Cross-encoder (transformer, bi-directional attention over query+passage)
- **Parameters**: 1 billion
- **Precision**: BF16
- **Disk size**: ~2 GB
- **VRAM required**: ~2–4 GB (GPU, BF16)
- **Max context**: 8,192 tokens
- **Benchmark (BEIR+TechQA Recall@5, paired with embed-1b-v2)**: 73.64%
- **Multilingual (MIRACL Recall@5)**: 65.80%
- **License**: NVIDIA Open Model License + Llama 3.2 — **commercial use allowed**

```python
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

model_name = "nvidia/llama-nemotron-rerank-1b-v2"

tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForSequenceClassification.from_pretrained(
    model_name,
    trust_remote_code=True,
    torch_dtype=torch.bfloat16,
).eval().cuda()  # use GPU

query = "What topics did the creator cover this week?"
documents = ["chunk1...", "chunk2...", "chunk3..."]

def make_prompt(q, p):
    return f"question:{q} \n \n passage:{p}"

texts = [make_prompt(query, d) for d in documents]
inputs = tokenizer(texts, padding=True, truncation=True,
                   return_tensors="pt", max_length=512).to("cuda")

with torch.inference_mode():
    scores = model(**inputs).logits.view(-1).tolist()

ranked = sorted(zip(documents, scores), key=lambda x: x[1], reverse=True)
```

### 4.3 GPU Memory Management (4GB VRAM)

The two NVIDIA 1B models together require ~4GB VRAM in BF16. To stay within budget:

- **At ingestion time**: Load only the embedding model. Generate all vectors. Unload. BM42 runs on CPU via FastEmbed.
- **At query time**: Load only the reranking model. Hybrid search (embedding lookup is a dot product against stored vectors, not a model inference call at query time). Rerank candidates. Unload.
- **If both must be loaded simultaneously**: Apply `bitsandbytes` INT8 quantization to reduce each model to ~1GB.

```python
from transformers import BitsAndBytesConfig

quant_config = BitsAndBytesConfig(load_in_8bit=True)
model = AutoModelForSequenceClassification.from_pretrained(
    "nvidia/llama-nemotron-rerank-1b-v2",
    quantization_config=quant_config,
    trust_remote_code=True
)
```

### 4.4 Fallback Models (if NVIDIA models underperform)

**Embedding fallback: BAAI/bge-m3**
- 568M parameters, ~2.3GB, GPU or CPU
- Strong MTEB retrieval scores, well-tested in production RAG
- Apache 2.0 license
- 8,192 token context
- Handles dense, sparse (BM25-style), and ColBERT-style retrieval in one model

**Reranking fallback: BAAI/bge-reranker-v2-m3**
- 568M parameters, ~1.1GB GPU
- Apache 2.0 license
- BEIR nDCG@10: 53.17 (multilingual average)
- ~0.5 sec per batch of 20 on CPU (much faster on GPU)

**Fast CPU reranking fallback: cross-encoder/ms-marco-MiniLM-L6-v2**
- 22.7M parameters, ~85MB
- nDCG@10: 74.30 on TREC DL 19
- ~55ms for 50 candidates on CPU
- Apache 2.0 license
- 42M monthly downloads — most battle-tested cross-encoder available

### 4.5 Models Ruled Out

| Model | Why Ruled Out |
|---|---|
| `nvidia/NV-Embed-v2` (8B) | Requires 24–48GB VRAM. OOM on RTX 4090. No GGUF available. Non-commercial license. |
| `nvidia/llama-embed-nemotron-8b` | Requires ~80GB VRAM (A100/H100). Flash-attn GPU dependency. Non-commercial license. |
| `jinaai/jina-reranker-v2-base-multilingual` | CC-BY-NC-4.0 — non-commercial only. |
| Cohere Rerank | Paid API. User wants to avoid paid APIs beyond Gemini. |

---

## 5. Pipeline Architecture Overview

```
Creator natural language query
        │
        ▼
┌─────────────────────────┐
│  LLM Query Classifier   │  (Gemini / Claude via LangChain tool use)
│  Detects query type:    │  → aggregation / keyword / semantic / cross-video
│  Extracts:              │  → video_id mentions
│                         │  → timecode language ("first 30s" → lte:30.0)
│                         │  → field hints ("jump cut" → cut_type filter)
│                         │  → production vs content query type
└─────────┬───────────────┘
          │
    ┌─────┴──────┐
    │            │
    ▼            ▼
Path 1:      Path 2:        Path 3:              Path 4:
Metadata     BM25           Semantic             Cross-video
Aggregate    Keyword        (single-hop)         Comparison
    │            │              │                    │
    ▼            ▼              ▼                    ▼
Qdrant       video_id      video_id pre-filter   Decompose into
payload      pre-filter    + field filters       N sub-queries
filter       → sparse      → Qdrant hybrid:      (one per video_id)
COUNT/SUM/   BM25 on       BM42 sparse (full     Each runs Path
GROUP BY     transcript    JSON) + dense         1, 2, or 3
             + overlay     (transcript OR        independently
             text          production)           → LLM synthesizes
                           → MMR (λ=0.7)         across results
                           → NVIDIA reranker
                             top-30 → top-10
                           → LLM generates
                             answer
```

---

## 6. Dense Embedding Strategy

### The Three Vectors: What Each One Is and Why It Exists

Each segment is stored in Qdrant with three vectors: two dense and one sparse. Before going into the dense embedding strategy in depth, here is what each one is and why it exists — built from first principles.

**What a dense vector is:** A dense vector is a fixed-length list of floating point numbers (e.g. 4096 numbers). An embedding model reads a piece of text and outputs this list. The key property is that two pieces of text that mean the same thing — even if worded differently — end up with lists of numbers that are geometrically close to each other. Qdrant can find the closest vectors to a query vector by traversing its HNSW graph. This is what makes semantic search possible.

**`dense_transcript`** embeds the spoken words and the factual one-line summary of what is happening in the segment. When you query this vector, you are asking: *"which segments have content that means something similar to my query?"* Example: "creator explains what an AI agent does" finds segments where the creator discusses AI agents, even if they never use those exact words.

**`dense_production`** embeds a natural language sentence built from the production metadata: shot type, camera angle, lighting, color grade, music, editing cuts, etc. (see `build_production_description()`). When you query this vector, you are asking: *"which segments have a visual and audio style that matches my query?"* Example: "cinematic and dramatic" finds segments with wide shots, low key lighting, slow camera movement, and dramatic music — even though none of those words appear in the transcript. These are two different semantic spaces and they must be kept separate. Mixing them into one vector degrades both.

**`sparse_minicoil`** is a learned sparse vector. It assigns importance weights to the tokens in the text and stores only the non-zero weights (indices + values). Unlike dense vectors which capture meaning, sparse vectors capture lexical presence — which specific tokens appear and how important they are. The miniCOIL model uses transformer attention to determine importance, making it smarter than raw BM25/TF-IDF, but the fundamental nature is still lexical.

**Sparse is NOT the same as a structural keyword filter.** A structural filter (via payload indexes, Section 8) is exact and boolean: it either matches a field value or it doesn't, and it gates which points are considered at all. Sparse is a ranked signal: it scores higher for lexical matches but still returns all queried points with a score. It is part of the relevance ranking system, not a filter.

**How all three work together in hybrid search:**

When a semantic query arrives, all three run in parallel as Prefetch candidates, then fuse via RRF (Reciprocal Rank Fusion):

```
sparse_minicoil  →  lexical/keyword signal on transcript  ┐
dense_transcript →  semantic match on speech content      ├── RRF fusion → final ranked list
dense_production →  semantic match on production style    ┘
```

A segment scores well if it is a strong match on any of the three signals. This is why hybrid consistently outperforms pure dense or pure sparse alone — they each fire on different aspects of relevance.

---

### The Core Decision: Two Named Dense Vectors Per Segment

We use **two separate named dense vectors** per segment point in Qdrant. This is the most important architecture decision in the pipeline.

**`dense_transcript`**: Embeds the contextual prefix + speech transcript. Used for queries about what was said — hook content, CTA phrasing, topic coverage, specific spoken claims, energy or tone of the speech.

**`dense_production`**: Embeds a curated natural-language description of all structured production fields. Used for queries about visual/audio style — cinematic feel, production quality, lighting mood, editing pace, music atmosphere.

### Why Two Vectors, Not One

**Option A (transcript only, single vector)**: Clean semantic signal for speech queries. But semantic search for "find my most cinematic moments" returns segments where the creator said the word "cinematic," not segments with cinematic production signals (low angle + soft light + shallow DoF + slow camera + desaturated grade).

**Option C (single enriched vector, everything combined)**: Mixes field-label tokens ("shot_type", "camera_angle") with natural speech. Embedding models optimized for natural language degrade when field labels pollute the semantic space. Speech-content queries compete against production-label tokens in the same embedding space.

**Option B (two named vectors — chosen)**: Keeps the two semantic spaces clean and independently queryable. The agent decides which vector to query based on whether the question is about content (what was said) or production (how it looks/sounds). Qdrant supports multiple named dense vectors natively with no extra collection needed.

### The Production Description Template

For each segment, `dense_production` is built from this template:

```python
def build_production_description(segment: dict) -> str:
    parts = []

    # Frame
    shot = segment["frame"]["shot_type"]
    angle = segment["frame"]["camera_angle"]
    movement = segment["frame"]["camera_movement"]
    parts.append(f"{shot} shot, {angle}, {movement} camera.")

    # Depth of field
    dof = segment["frame"].get("depth_of_field", "[unclear]")
    if dof != "[unclear]":
        parts.append(f"{dof} depth of field.")

    # Lighting
    lq = segment["lighting"]["light_quality"]
    ct = segment["lighting"]["color_temperature_feel"]
    notable = segment["lighting"]["notable"]
    notable_str = f", {notable}" if notable not in ["none", "[none]", ""] else ""
    parts.append(f"{lq} {ct} lighting{notable_str}.")

    # Background
    bg_desc = segment["background"]["description"]
    parts.append(f"Background: {bg_desc}.")

    # Music
    music = segment["audio"]["music"]
    if music["present"]:
        tempo = music["tempo_feel"]
        genre = music["genre_feel"]
        change = music["notable_change"]
        change_str = f", {change}" if change not in ["none", "[none]", ""] else ""
        parts.append(f"Music: {tempo} {genre}{change_str}.")
    else:
        parts.append("No background music.")

    # Editing
    cut = segment["editing"]["cut_event"]["type"] if segment["editing"]["cut_event"]["occurred"] else "no cut"
    speed = segment["editing"]["speed_change"]
    speed_str = f", {speed}" if speed not in ["none", "[none]", ""] else ""
    parts.append(f"Edit: {cut}{speed_str}.")

    # Production observables
    grade = segment["production_observables"]["color_grade_feel"]
    mic = segment["production_observables"]["microphone_type_inferred"]
    parts.append(f"{grade} color grade. {mic} microphone.")

    # On-screen text
    if segment["on_screen_text"]["present"]:
        texts = [e["text"] for e in segment["on_screen_text"]["entries"]]
        parts.append(f"On-screen text: {' | '.join(texts)}.")

    # Graphics
    if segment["graphics_and_animations"]["present"]:
        types = [e["type"] for e in segment["graphics_and_animations"]["entries"]]
        parts.append(f"Graphics: {', '.join(types)}.")

    return " ".join(parts)
```

Example output for a typical talking-head segment:
> "CU shot, eye-level, static camera. Shallow depth of field. Soft warm lighting. Background: blurred bookshelf, warm tones. Music: slow ambient. Edit: hard-cut. Warm color grade. Shotgun microphone. On-screen text: BIGGEST MISTAKE."

This is ~30 tokens of clean natural language. "Cinematic" queries find low-angle + soft light + slow camera segments. "High energy" queries find fast tempo + bright color grade + jump-cut segments. The embedding model handles this text form well.

### Which Vector to Query Per Query Type

| Query type | Vector used | Example |
|---|---|---|
| What did the creator say about X | `dense_transcript` | "When does the creator talk about equipment?" |
| How does the hook sound | `dense_transcript` | "What does the creator say in the first 10 seconds?" |
| Energy / tone of speech | `dense_transcript` | "When does the creator sound disengaged?" |
| Visual style / cinematic feel | `dense_production` | "Find my most cinematic moments" |
| Production quality | `dense_production` | "Segments with professional-looking lighting" |
| Music atmosphere | `dense_production` | "When does the music feel tense or dramatic?" |
| Editing pace / rhythm | `dense_production` | "Where is the editing the most energetic?" |
| Ambiguous (could be either) | Both (query both, RRF-fuse results) | "When does this video feel high quality?" |

---

## 7. Sparse BM42 Strategy

### Why BM42 Over BM25

BM25 was designed for long documents where term frequency (TF) is a meaningful signal. In RAG systems, all chunks are short and roughly fixed-length (our segments: 50–200 words). In this regime, TF is statistically unreliable — a word appearing twice in a 100-word chunk vs. once does not carry the same information as it would in a 5,000-word article.

BM42 (Qdrant, July 2024) replaces the TF component with **transformer attention weights** from a small model's `[CLS]` token. The scoring formula is:

```
score(D, Q) = Σ IDF(q_i) × Attention(CLS → q_i)
```

BM42 treats tokens as more important when the document's `[CLS]` token attends strongly to them — a semantically grounded weight rather than a raw count.

Benchmarks:
- BM42 Precision@10: 0.49 vs BM25 0.45 (+8.9%)
- BM42 Recall@10: 0.85 vs BM25 0.89 (slight regression — BM42 is more precise, less broad)
- Average non-zero elements: 5.6 per document (very sparse — fast index, small footprint)

For short segment documents, BM42 precision gain outweighs the slight recall regression. The reranker compensates for recall gaps.

**Qdrant FastEmbed model**: `Qdrant/bm42-all-minilm-l6-v2-attentions`

### What Gets BM42 Indexed

The full serialized segment JSON goes into the sparse index:

```python
import json

sparse_input = json.dumps(segment)
# Result: all field names, all values, all transcript text — everything tokenized and indexed
```

This means:
- BM25/BM42 can find a segment by field value: `"jump-cut"`, `"lo-fi"`, `"MCU"`
- BM25/BM42 can find a segment by exact spoken phrase: `"I posted the same video twice"`
- BM25/BM42 can find a segment by on-screen text: `"BIGGEST MISTAKE"`
- Field name tokens (`"shot_type"`, `"camera_angle"`) are noise but are stopword-filtered or down-weighted by IDF because they appear in every document

Alternative considered: Two separate sparse vectors (one for transcript only, one for full JSON). Adds complexity. The full JSON approach is simpler to maintain and the noise from field labels is mitigated by IDF weighting (they appear in every document, so IDF ≈ 0). Revisit if retrieval quality shows field-label interference.

---

## 8. Qdrant Collection Schema

### Collection vs Payload Index: First Principles

Qdrant stores objects called **points**. Each point has three things: an ID, one or more vectors (lists of floats), and a payload (a flat JSON object with arbitrary key-value pairs). When we index a segment, one point is created. That point's payload contains every piece of data from the segment flattened out: `shot_type`, `music_present`, `transcript`, `project_id`, `duration_seconds`, etc.

**`create_collection()` — defines the structure of the database itself.**

Before you can store any points, Qdrant needs to know: how many dimensions do the vectors have? What distance metric? What are the named vector slots? `create_collection()` answers those questions. It sets up the HNSW graph (the data structure Qdrant uses to find nearest neighbors fast) with the correct dimensions and configuration. After this call, you can start inserting points. The payloads get stored as raw JSON blobs alongside each point.

**`create_payload_index()` — builds a fast lookup structure for a specific payload field.**

Without a payload index, filtering by a field requires a full scan: Qdrant opens every single point, deserializes its payload, checks the field value, and either keeps or discards it. For a collection with 100,000 segments, filtering by `shot_type = "MCU"` reads 100,000 points.

`create_payload_index()` tells Qdrant: "build a dedicated lookup structure for this field." For a keyword field like `shot_type`, Qdrant maintains an inverted index in memory:

```
"MCU"          → [point_id_3, point_id_7, point_id_19, ...]
"WS"           → [point_id_1, point_id_12, ...]
"B-roll"       → [point_id_2, point_id_5, ...]
```

For a boolean like `music_present`: two buckets, `true → [...]` and `false → [...]`. For a float like `duration_seconds`: a sorted structure so range queries (`>= 5.0 AND <= 10.0`) resolve via binary search instead of a scan.

**Who does the structural filtering — Qdrant or our code?** Qdrant does it entirely. Our code builds a `Filter` object in Python (just a description of what we want), passes it to `client.scroll(scroll_filter=...)`, and Qdrant executes it on its side using its payload indexes, returning only matching points. We never download all points and filter in Python.

The `StructuralFilters` dataclass in our code is a convenience object. The `_build_filter()` function converts it to the Qdrant `Filter` format. Once passed to Qdrant, our code is done — Qdrant takes over completely.

**Why payload indexes must be created BEFORE any upsert:** If you upsert first and create indexes after, existing points are NOT indexed. The index only applies to points inserted after it was created. Always call `ensure_collection()` (which creates both the collection and all indexes) before inserting any data.

---

### Collection Configuration

```python
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, SparseVectorParams, SparseIndexParams,
    Distance, HnswConfigDiff, Modifier, PayloadIndexParams,
    PayloadSchemaType, TextIndexParams, TokenizerType
)

client = QdrantClient(host="localhost", port=6333)

client.create_collection(
    collection_name="video_segments",
    vectors_config={
        "dense_transcript": VectorParams(
            size=2048,           # nvidia llama-nemotron-embed-1b-v2 default dim
            distance=Distance.COSINE,
            hnsw_config=HnswConfigDiff(
                m=16,            # connections per node (default=16, range 4-64)
                ef_construct=100 # build-time neighbors checked (default=100)
            )
        ),
        "dense_production": VectorParams(
            size=2048,
            distance=Distance.COSINE,
            hnsw_config=HnswConfigDiff(m=16, ef_construct=100)
        ),
    },
    sparse_vectors_config={
        "sparse_bm42": SparseVectorParams(
            index=SparseIndexParams(
                on_disk=False,           # keep in RAM for query speed
                full_scan_threshold=5000
            ),
            modifier=Modifier.IDF        # IDF weighting for BM42
        )
    }
)
```

### Payload Indexes (MUST create before any upsert)

```python
# Keyword indexes (exact match, enum fields)
for field in [
    "video_id", "shot_type", "camera_angle", "camera_movement",
    "cut_type", "transition_effect", "speed_change",
    "audio_quality", "music_tempo_feel", "music_genre_feel",
    "light_quality", "color_temperature_feel", "color_grade_feel",
    "speaker_id", "microphone_type_inferred", "platform",
    "aspect_ratio", "resolution"
]:
    client.create_payload_index(
        collection_name="video_segments",
        field_name=field,
        field_schema=PayloadSchemaType.KEYWORD
    )

# Boolean indexes
for field in [
    "on_screen_text_present", "graphics_present",
    "music_present", "sound_effects_present", "speaker_visible"
]:
    client.create_payload_index(
        collection_name="video_segments",
        field_name=field,
        field_schema=PayloadSchemaType.BOOL
    )

# Float indexes (for range queries on timecodes)
for field in [
    "timecode_start_seconds", "timecode_end_seconds", "duration_seconds"
]:
    client.create_payload_index(
        collection_name="video_segments",
        field_name=field,
        field_schema=PayloadSchemaType.FLOAT
    )

# Integer index (segment ordering)
client.create_payload_index(
    collection_name="video_segments",
    field_name="segment_id",
    field_schema=PayloadSchemaType.INTEGER
)

# Text index for full-text search on transcript
client.create_payload_index(
    collection_name="video_segments",
    field_name="transcript_text",
    field_schema=TextIndexParams(
        type="text",
        tokenizer=TokenizerType.WORD,
        min_token_len=2,
        max_token_len=20,
        lowercase=True
    )
)

# Tenant optimization: video_id co-location on disk
client.create_payload_index(
    collection_name="video_segments",
    field_name="video_id",
    field_schema=PayloadSchemaType.KEYWORD,
    # Note: set is_tenant=True in Qdrant config for co-location
)
```

### Payload Structure Per Point

```python
payload = {
    # Identity
    "video_id": "yt_abc123",
    "segment_id": 47,
    "project_id": "project_uuid",   # for multi-project isolation if needed

    # Timecodes (stored as seconds for range queries)
    "timecode_start_seconds": 92.0,
    "timecode_end_seconds": 97.0,
    "duration_seconds": 5.0,
    "timecode_start_display": "01:32",
    "timecode_end_display": "01:37",

    # Frame
    "shot_type": "CU",
    "camera_angle": "eye-level",
    "camera_movement": "static",
    "depth_of_field": "shallow",

    # Audio
    "audio_quality": "clean-studio",
    "music_present": True,
    "music_tempo_feel": "slow",
    "music_genre_feel": "ambient",
    "sound_effects_present": False,

    # Editing
    "cut_type": "hard-cut",
    "transition_effect": "none",
    "speed_change": "none",

    # Lighting
    "light_quality": "soft",
    "color_temperature_feel": "warm",

    # Production
    "color_grade_feel": "warm",
    "microphone_type_inferred": "shotgun",

    # Presence booleans
    "on_screen_text_present": True,
    "graphics_present": False,
    "speaker_visible": True,
    "speaker_id": "Speaker_A",

    # Video-level metadata
    "platform": "youtube",
    "creator_name": "Creator Example",
    "video_title": "I Tried Every Hook Strategy For 30 Days",
    "upload_date": "2024-11-15",
    "aspect_ratio": "16:9",

    # Full content (for LLM context window after retrieval)
    "transcript_text": "I posted the same video twice.",
    "full_segment_json": "{...full json string...}",

    # Neighbor retrieval support
    "prev_segment_id": 46,
    "next_segment_id": 48,
}
```

---

## 9. Ingestion Pipeline

### Step-by-Step Per Segment

```python
from sentence_transformers import SentenceTransformer
from fastembed import SparseTextEmbedding
import torch

# Load embedding model (GPU, load once)
embed_model = SentenceTransformer(
    "nvidia/llama-nemotron-embed-1b-v2",
    trust_remote_code=True,
    device="cuda"
)

# Load BM42 sparse model (CPU, lightweight)
sparse_model = SparseTextEmbedding(model_name="Qdrant/bm42-all-minilm-l6-v2-attentions")

def ingest_segment(segment: dict, video_meta: dict):
    # --- Step 1: Generate contextual prefix (Gemini with prompt caching) ---
    context_prefix = generate_context_prefix(segment, video_meta)
    # e.g. "Segment 47 of 'I Tried Every Hook Strategy For 30 Days' by Creator Example,
    #        CU shot at 01:32, creator discussing their experiment results."

    # --- Step 2: Dense transcript vector ---
    transcript_input = context_prefix + " " + segment["speech"]["transcript"]
    dense_transcript_vec = embed_model.encode_document(
        [transcript_input], convert_to_tensor=True
    )[0].tolist()

    # --- Step 3: Dense production vector ---
    production_description = build_production_description(segment)
    dense_production_vec = embed_model.encode_document(
        [production_description], convert_to_tensor=True
    )[0].tolist()

    # --- Step 4: Sparse BM42 vector (full JSON) ---
    full_json_str = json.dumps(segment)
    sparse_result = list(sparse_model.embed([full_json_str]))[0]
    sparse_vec = {
        "indices": sparse_result.indices.tolist(),
        "values": sparse_result.values.tolist()
    }

    # --- Step 5: Build payload ---
    payload = build_payload(segment, video_meta)

    # --- Step 6: Upsert to Qdrant ---
    client.upsert(
        collection_name="video_segments",
        points=[PointStruct(
            id=str(uuid4()),
            vector={
                "dense_transcript": dense_transcript_vec,
                "dense_production": dense_production_vec,
                "sparse_bm42": sparse_vec,
            },
            payload=payload
        )]
    )
```

### Contextual Prefix Generation

The contextual prefix is a short LLM-generated sentence (Gemini, with prompt caching) prepended to the transcript before embedding. It provides document-level context that the isolated chunk would otherwise lack.

This is Anthropic's "Contextual Retrieval" technique (September 2024), which demonstrated:
- 35% reduction in retrieval failure rate from contextual embeddings alone
- 49% reduction with contextual embeddings + contextual BM25
- 67% reduction when reranking is added on top
- Cost: ~$1.02 per million document tokens with prompt caching

Format:
```
"Segment {N} of '{video_title}' by {creator_name}, {shot_type} shot at {timecode_start}.
[One LLM-generated sentence describing what is happening in this specific segment
in the context of the video as a whole.]"
```

The LLM is given the full video's segment list as context (via prompt caching — the video context is cached, only the per-segment instruction changes). This is cheap because the long context (the full video JSON) is cached across all segment prefix generations for one video.

#### Alternative: Late Chunking (No LLM Calls at Ingestion)

If Gemini call cost at ingestion is a concern, use late chunking instead:
- Pass all segments from one video through a long-context embedding model (Jina Embeddings v2, 8192 token window) as one batch
- Apply mean-pooling per segment after the transformer forward pass
- Preserves cross-segment token attention for free — no LLM call needed
- Implementation: ~30 lines of change to the embedding step
- Tradeoff: requires a long-context embedding model (Jina v2 specifically supports this); our NVIDIA 1B model may not support it the same way

---

## 10. Hybrid Search and Fusion

### The Query Call (Qdrant Python Client Directly)

Do not use LangChain's `QdrantVectorStore.similarity_search()` for the actual search. It locks you to RRF with default parameters and no fusion tuning. Use the Qdrant Python client directly:

```python
from qdrant_client.models import (
    Prefetch, Query, FusionQuery, Fusion,
    Filter, FieldCondition, MatchValue, Range, SparseVector
)

def hybrid_search(
    nl_query: str,
    query_vector_name: str,   # "dense_transcript" or "dense_production"
    filters: dict,            # structured payload filters from agent
    top_k: int = 10,
    prefetch_k: int = 50,     # overfetch before reranking
):
    # Encode query to dense vector
    query_vec = embed_model.encode_query([nl_query])[0].tolist()

    # Encode query to sparse BM42 vector
    sparse_query = list(sparse_model.query_embed(nl_query))[0]
    sparse_query_vec = SparseVector(
        indices=sparse_query.indices.tolist(),
        values=sparse_query.values.tolist()
    )

    # Build Qdrant filter from agent-provided structured filters
    qdrant_filter = build_qdrant_filter(filters)

    results = client.query_points(
        collection_name="video_segments",
        prefetch=[
            Prefetch(
                query=sparse_query_vec,
                using="sparse_bm42",
                filter=qdrant_filter,   # pre-filter inside each prefetch
                limit=prefetch_k
            ),
            Prefetch(
                query=query_vec,
                using=query_vector_name,
                filter=qdrant_filter,   # same filter in dense prefetch
                limit=prefetch_k
            ),
        ],
        query=FusionQuery(fusion=Fusion.RRF),  # fuse the two prefetch results
        limit=top_k,
        with_payload=True,
        search_params=SearchParams(hnsw_ef=128)  # higher ef = better recall
    )

    return results.points
```

### RRF Fusion Parameters

RRF (Reciprocal Rank Fusion) is the standard fusion method. It uses ranks, not raw scores, so it normalizes across BM42 (which returns attention-weighted keyword scores) and dense (which returns cosine similarities). Raw scores are not comparable; RRF sidesteps this.

Formula: `score(d) = Σ weight_r / (k + rank_r(d))`

Tunable parameters:
- `k` (default=2): Controls the penalty curve between ranks. k=60 is a widely recommended value from the IR literature — reduces rank discrimination to allow lower-ranked candidates more influence. Start with k=60.
- `weights`: Per-prefetch multiplier array. E.g., `weights=[3.0, 1.0]` gives BM42 3x the influence of dense. Tune on a held-out creator query set.

### When to Use DBSF Instead of RRF

DBSF (Distribution-Based Score Fusion) normalizes raw scores using `mean ± 3σ` then sums. Use DBSF when both retrieval methods return well-calibrated relevance scores. For BM42 + dense, scores have very different distributions (BM42 returns attention weights, dense returns cosine similarities). RRF is the safer default.

Switch to DBSF only if you observe that RRF is over-weighting BM42 results on low-keywordness queries.

### Filterable HNSW — How Qdrant's Filtering Actually Works

Qdrant's filtering is neither pure pre-filter nor pure post-filter. It uses **filterable HNSW with in-algorithm filtering**:

- When payload indexes are created BEFORE data upload, Qdrant builds additional edges in the HNSW graph based on payload values ("orange links"). This maintains graph traversability even when many nodes are filtered.
- At query time, the query planner switches strategy based on filter cardinality:
  - High cardinality filter (matches many points): Regular HNSW traversal, non-matching nodes skipped dynamically.
  - Low cardinality filter (matches few points): Bypasses HNSW entirely, uses payload index + full scan. Often faster for very selective filters.
- Since v1.16: ACORN algorithm — for complex multi-filter scenarios, explores second-hop neighbors when direct neighbors are filtered out.

**Practical implication**: `video_id` filter is extremely high selectivity (narrows to one video's ~100-150 segments out of potentially thousands). This will trigger the full-scan strategy — fast and precise. `shot_type = "CU"` is lower selectivity and will use HNSW traversal.

---

## 11. Reranking

### Why Reranking Is Mandatory

Bi-encoder retrieval (embedding similarity) gives a coarse first-pass ranking. The NVIDIA embed model produces one vector per chunk and computes one dot product per query. This cannot capture the nuanced relevance relationship between a complex creator question and a specific video segment.

Cross-encoder rerankers see both the query and each candidate simultaneously — enabling genuine attention over the query-document pair. This is why:
- Hybrid search typically gives 15–30% precision improvement over vector-only RAG
- Reranking on top of hybrid gives another 15–25% relevant-in-top-5 improvement
- The combined effect of hybrid + reranking has been described as "the most impactful single change" and "highest ROI improvement" across multiple practitioner reports and RAGFlow's 2024/2025 review

### Latency Reality (from ZeroEntropy benchmarks, 17 datasets)

| Method | Latency (75KB input) | NDCG@10 |
|---|---|---|
| Cross-encoder (zerank-1) | 129.7ms | 0.777 |
| GPT-4o-mini (listwise) | 1,090ms | ~0.70 |
| GPT-5-mini (listwise) | 2,180ms | similar |

Cross-encoders are 8–17x faster than LLM-based reranking and 10–24x cheaper. Use cross-encoders.

### Reranking Implementation

```python
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

reranker_name = "nvidia/llama-nemotron-rerank-1b-v2"
reranker_tokenizer = AutoTokenizer.from_pretrained(reranker_name, trust_remote_code=True)
if reranker_tokenizer.pad_token is None:
    reranker_tokenizer.pad_token = reranker_tokenizer.eos_token

reranker_model = AutoModelForSequenceClassification.from_pretrained(
    reranker_name,
    trust_remote_code=True,
    torch_dtype=torch.bfloat16,
).eval().cuda()

def rerank(query: str, candidates: list[dict], top_n: int = 10) -> list[dict]:
    documents = [c["payload"]["full_segment_json"] for c in candidates]

    def make_prompt(q, p):
        return f"question:{q} \n \n passage:{p}"

    pairs = [make_prompt(query, doc) for doc in documents]
    inputs = reranker_tokenizer(
        pairs, padding=True, truncation=True,
        return_tensors="pt", max_length=512
    ).to("cuda")

    with torch.inference_mode():
        scores = reranker_model(**inputs).logits.view(-1).tolist()

    ranked = sorted(
        zip(candidates, scores),
        key=lambda x: x[1],
        reverse=True
    )
    return [item[0] for item in ranked[:top_n]]
```

### Reranking Pipeline Position

```
Hybrid search → top-50 candidates
    → MMR diversification (remove near-duplicates, λ=0.7) → ~30 candidates
    → Cross-encoder reranker → top-10
    → LLM receives top-10 segments as context
```

The reranker receives the full serialized segment JSON as the "passage" — not just the transcript. This gives it access to all production metadata when scoring relevance, not just spoken content.

---

## 12. Query Routing: The Four Paths

### Path 1: Metadata Aggregate (25% of queries)

**Trigger**: Creator wants a count, sum, duration total, or frequency distribution over structured fields.

**Examples**:
- "How many jump cuts does my video have?"
- "What's the total B-roll time in this video?"
- "How many segments have on-screen text?"
- "What's my most common shot type?"
- "Which of my videos has the most camera movement?"

**Retrieval**: No vector search. Qdrant payload filter + client-side aggregation.

```python
# Example: count jump cuts
results = client.scroll(
    collection_name="video_segments",
    scroll_filter=Filter(must=[
        FieldCondition(key="video_id", match=MatchValue(value="yt_abc123")),
        FieldCondition(key="cut_type", match=MatchValue(value="jump-cut"))
    ]),
    with_payload=True,
    limit=10000
)
count = len(results[0])

# Example: sum B-roll duration
results = client.scroll(
    collection_name="video_segments",
    scroll_filter=Filter(must=[
        FieldCondition(key="video_id", match=MatchValue(value="yt_abc123")),
        FieldCondition(key="shot_type", match=MatchValue(value="B-roll"))
    ]),
    with_payload=["duration_seconds"],
    limit=10000
)
total_broll_seconds = sum(p.payload["duration_seconds"] for p in results[0])
```

**Note**: Qdrant does not have server-side aggregation (COUNT, SUM, GROUP BY). Fetch all matching points, aggregate client-side. For collections of hundreds of segments per video, this is fast. At millions of segments, revisit.

### Path 2: BM25 Keyword Search (20% of queries)

**Trigger**: Creator asks about an exact word or phrase — something they said, or text that appeared on screen.

**Examples**:
- "When did I say 'subscribe'?"
- "Find every segment where I said the word 'mistake'"
- "Show me all on-screen text that says 'link in bio'"
- "When did my competitor mention 'NordVPN'?"

**Retrieval**: `video_id` pre-filter + BM42 sparse-only search (no dense vector).

```python
results = client.query_points(
    collection_name="video_segments",
    prefetch=[
        Prefetch(
            query=sparse_query_vec,
            using="sparse_bm42",
            filter=Filter(must=[
                FieldCondition(key="video_id", match=MatchValue(value="yt_abc123"))
            ]),
            limit=20
        )
    ],
    query=sparse_query_vec,  # no fusion, just sparse
    using="sparse_bm42",
    limit=10,
    with_payload=True
)
```

For on-screen text specifically, the Qdrant `full_text_match` condition on the `transcript_text` payload index can also be used for sub-millisecond exact phrase lookup.

### Path 3: Semantic Search (35% of queries)

**Trigger**: Creator describes a concept, feeling, quality, or production attribute that cannot be matched by exact keywords.

**Examples**:
- "When does my energy feel low or flat?"
- "Find moments where I'm building emotional tension"
- "When does this look the most cinematic?"
- "Find my competitor's strongest CTA moments"
- "When does the video feel like it's losing momentum?"

**Retrieval**: Full hybrid pipeline (pre-filter → BM42 + dense → MMR → rerank).

The query classifier also determines `search_vector`:
- Content/speech queries → `dense_transcript`
- Production/visual/audio queries → `dense_production`
- Ambiguous → both (query both named vectors in separate prefetches, 4-way RRF fusion)

### Path 4: Cross-Video Comparison (20% of queries)

**Trigger**: Creator compares two or more videos — either their own vs a competitor, or across their own video library.

**Examples**:
- "Compare my hook structure to this competitor's"
- "Which of my videos has the highest B-roll density?"
- "Do I use more on-screen text than Creator X?"
- "Who gets to the point faster, me or my competitor?"
- "Find close-up emotional moments across all three videos"

**Retrieval**: Query decomposition. The agent issues sub-queries (Path 1, 2, or 3) per `video_id` independently, collects per-video results, then synthesizes.

This CANNOT be a single RAG call. Mixing all videos into one semantic search and asking for comparison produces unreliable results — the model cannot reliably attribute retrieved segments to specific videos or make fair per-video comparisons.

---

## 13. Agent Tool Design and Query Object Schema

### The Four Tools (LLM Function Calling)

```python
tools = [
    {
        "name": "aggregate_metadata",
        "description": (
            "Count, sum, or group video segments by structured field values. "
            "Use for any question asking HOW MANY, HOW MUCH TIME, MOST COMMON, "
            "TOTAL DURATION of a specific production element. "
            "No vector search involved — purely deterministic."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "video_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "One or more video_id values. Pass ['all'] to query across all videos in the project."
                },
                "filters": {
                    "type": "object",
                    "description": "Structured field filters to apply before aggregation.",
                    "properties": {
                        "shot_type": {"type": "array", "items": {"type": "string"}},
                        "cut_type": {"type": "array", "items": {"type": "string"}},
                        "camera_movement": {"type": "array", "items": {"type": "string"}},
                        "on_screen_text_present": {"type": "boolean"},
                        "graphics_present": {"type": "boolean"},
                        "music_present": {"type": "boolean"},
                        "music_tempo_feel": {"type": "string"},
                        "music_genre_feel": {"type": "string"},
                        "light_quality": {"type": "string"},
                        "color_temperature_feel": {"type": "string"},
                        "audio_quality": {"type": "string"},
                        "speaker_id": {"type": "string"},
                        "speed_change": {"type": "string"},
                        "timecode_start_gte_seconds": {"type": "number"},
                        "timecode_start_lte_seconds": {"type": "number"},
                    }
                },
                "operation": {
                    "type": "string",
                    "enum": ["COUNT", "SUM_duration", "GROUP_BY"],
                    "description": "COUNT returns number of matching segments. SUM_duration returns total seconds. GROUP_BY counts per unique value of group_by_field."
                },
                "group_by_field": {
                    "type": "string",
                    "description": "Required when operation is GROUP_BY. Field to group results by."
                }
            },
            "required": ["video_ids", "operation"]
        }
    },
    {
        "name": "keyword_search",
        "description": (
            "Find segments containing an exact word or phrase in spoken transcript "
            "or on-screen text. Use when the creator asks about a specific word they "
            "said, a phrase that appears on screen, or a product/brand name."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "video_ids": {"type": "array", "items": {"type": "string"}},
                "phrase": {"type": "string", "description": "Exact word or phrase to match."},
                "search_in": {
                    "type": "string",
                    "enum": ["transcript", "on_screen_text", "both"],
                    "default": "transcript"
                },
                "timecode_start_gte_seconds": {"type": "number"},
                "timecode_start_lte_seconds": {"type": "number"}
            },
            "required": ["video_ids", "phrase"]
        }
    },
    {
        "name": "semantic_search",
        "description": (
            "Find segments by meaning, feel, concept, or production quality — "
            "when the query describes something that may not appear word-for-word "
            "in the transcript. Use dense_transcript for content/speech queries. "
            "Use dense_production for visual/audio/production queries like 'cinematic', "
            "'high energy', 'professional looking', 'dramatic music'. "
            "Use both when the query could involve either."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "video_ids": {"type": "array", "items": {"type": "string"}},
                "nl_query": {"type": "string", "description": "Natural language description of what to find."},
                "search_vector": {
                    "type": "string",
                    "enum": ["dense_transcript", "dense_production", "both"],
                    "default": "dense_transcript"
                },
                "filters": {
                    "type": "object",
                    "description": "Optional pre-filters to narrow the search space before semantic search.",
                    "properties": {
                        "shot_type": {"type": "array", "items": {"type": "string"}},
                        "on_screen_text_present": {"type": "boolean"},
                        "music_present": {"type": "boolean"},
                        "timecode_start_gte_seconds": {"type": "number"},
                        "timecode_start_lte_seconds": {"type": "number"},
                        "camera_movement": {"type": "array", "items": {"type": "string"}},
                        "light_quality": {"type": "string"},
                        "cut_type": {"type": "array", "items": {"type": "string"}}
                    }
                },
                "top_k": {"type": "integer", "default": 10}
            },
            "required": ["video_ids", "nl_query"]
        }
    },
    {
        "name": "compare_across_videos",
        "description": (
            "Compare a metric, style element, or content aspect across two or more videos. "
            "This decomposes into per-video sub-queries and synthesizes the comparison. "
            "Use whenever the creator asks to compare their video to a competitor's, "
            "or to compare across multiple videos they've uploaded."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "video_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Must contain 2 or more video_id values."
                },
                "comparison_aspect": {
                    "type": "string",
                    "description": "What to compare in natural language."
                },
                "sub_query_type": {
                    "type": "string",
                    "enum": ["aggregate", "keyword", "semantic"],
                    "description": "Which retrieval path to use for each video's sub-query."
                },
                "sub_query_params": {
                    "type": "object",
                    "description": "Parameters for the sub-query, applied identically to each video. Same structure as the corresponding tool's parameters (minus video_ids)."
                }
            },
            "required": ["video_ids", "comparison_aspect", "sub_query_type"]
        }
    }
]
```

### Ten Creator Query Examples: Translated to Tool Calls

**1. "How many jump cuts are in my video?"**
```json
{
  "tool": "aggregate_metadata",
  "video_ids": ["my_video_007"],
  "filters": { "cut_type": ["jump-cut"] },
  "operation": "COUNT"
}
```

**2. "What's the total B-roll time in this video?"**
```json
{
  "tool": "aggregate_metadata",
  "video_ids": ["my_video_007"],
  "filters": { "shot_type": ["B-roll"] },
  "operation": "SUM_duration"
}
```

**3. "When did I say the word 'subscribe'?"**
```json
{
  "tool": "keyword_search",
  "video_ids": ["my_video_007"],
  "phrase": "subscribe",
  "search_in": "transcript"
}
```

**4. "When does my energy feel low or flat?"**
```json
{
  "tool": "semantic_search",
  "video_ids": ["my_video_007"],
  "nl_query": "creator sounds disengaged, flat, slow-paced, or low energy in delivery",
  "search_vector": "dense_transcript"
}
```

**5. "Find the most cinematic moments in my video"**
```json
{
  "tool": "semantic_search",
  "video_ids": ["my_video_007"],
  "nl_query": "high production value, cinematic look and feel, professional lighting and composition",
  "search_vector": "dense_production"
}
```

**6. "When does my competitor's sponsorship segment start?"**
```json
{
  "tool": "semantic_search",
  "video_ids": ["competitor_vid_003"],
  "nl_query": "creator stops main content and begins a paid brand integration or sponsored read",
  "search_vector": "dense_transcript"
}
```
*(This returns the timecode. The agent then issues a follow-up `aggregate_metadata` or `keyword_search` scoped to that timecode range if the creator asks follow-up questions about what happened during the sponsorship.)*

**7. "Which of these three videos has the most B-roll?"**
```json
{
  "tool": "compare_across_videos",
  "video_ids": ["my_vid_001", "competitor_vid_002", "competitor_vid_003"],
  "comparison_aspect": "total B-roll duration",
  "sub_query_type": "aggregate",
  "sub_query_params": {
    "filters": { "shot_type": ["B-roll"] },
    "operation": "SUM_duration"
  }
}
```

**8. "Compare my hook to my competitor's — who gets to the point faster?"**
```json
{
  "tool": "compare_across_videos",
  "video_ids": ["my_vid_001", "competitor_vid_002"],
  "comparison_aspect": "speed of reaching the core topic or value proposition",
  "sub_query_type": "semantic",
  "sub_query_params": {
    "nl_query": "first moment creator states the core topic, promise, or value of the video",
    "search_vector": "dense_transcript",
    "filters": { "timecode_start_lte_seconds": 60.0 },
    "top_k": 3
  }
}
```

**9. "Find all close-up emotional moments across all my uploaded videos"**
```json
{
  "tool": "semantic_search",
  "video_ids": ["all"],
  "nl_query": "creator speaking in a personal, vulnerable, or emotionally resonant way directly to the viewer",
  "search_vector": "dense_transcript",
  "filters": { "shot_type": ["ECU", "CU"] },
  "top_k": 20
}
```

**10. "What music atmosphere does my competitor use most?"**
```json
{
  "tool": "aggregate_metadata",
  "video_ids": ["competitor_vid_002"],
  "filters": { "music_present": true },
  "operation": "GROUP_BY",
  "group_by_field": "music_genre_feel"
}
```

### Timecode Parsing from Natural Language

Creators will say things like "in the first 30 seconds", "after the 2 minute mark", "in the intro", "during the hook". The query classifier LLM must parse these into numeric timecode filters.

Patterns to handle:
- "first N seconds" → `timecode_start_lte_seconds: N`
- "after N minutes" → `timecode_start_gte_seconds: N * 60`
- "around the X minute mark" → `timecode_start_gte_seconds: X*60 - 15, timecode_start_lte_seconds: X*60 + 15`
- "in the hook" → `timecode_start_lte_seconds: 30.0` (heuristic: hooks are first 30s)
- "in the intro" → `timecode_start_lte_seconds: 60.0`
- "in the outro" → retrieve video duration from document-level metadata, apply `timecode_start_gte_seconds: duration - 30`

These heuristics should be in the system prompt for the query classifier. The LLM should apply them as defaults and refine if the creator corrects.

---

## 14. Cross-Video Comparison Pattern

Cross-video comparison is the hardest retrieval pattern. It requires:
1. Decomposing the query into per-video sub-queries
2. Running each sub-query independently (with its own `video_id` pre-filter)
3. Collecting per-video results
4. Passing all per-video results to the LLM for comparative synthesis

```python
async def cross_video_compare(
    video_ids: list[str],
    comparison_aspect: str,
    sub_query_type: str,
    sub_query_params: dict
) -> str:
    per_video_results = {}

    for video_id in video_ids:
        params = {**sub_query_params, "video_ids": [video_id]}

        if sub_query_type == "aggregate":
            result = await aggregate_metadata(**params)
        elif sub_query_type == "keyword":
            result = await keyword_search(**params)
        elif sub_query_type == "semantic":
            result = await semantic_search(**params)

        per_video_results[video_id] = result

    # Pass per-video results to LLM for synthesis
    synthesis_prompt = build_comparison_prompt(
        comparison_aspect=comparison_aspect,
        per_video_results=per_video_results,
        video_metadata=get_video_metadata(video_ids)
    )
    return llm.invoke(synthesis_prompt)
```

### What NOT to Do

Do not issue a single semantic search with all `video_ids` and ask the LLM to compare. The retrieved segments will not be evenly distributed across videos. If Video A has more segments matching the semantic query, Video B will be underrepresented, and the comparison will be biased. Always decompose.

---

## 15. Neighbor Retrieval (Context Expansion)

Video content flows continuously. A retrieved segment may reference something from the previous segment ("as I mentioned just now...") or set up something in the next segment. Without the surrounding context, the LLM may misinterpret the retrieved content.

### Why Not Full Parent-Child Chunking

NVIDIA's internal tests showed parent-child chunking improved accuracy from 61% to 89% (on their document RAG benchmark). However, this technique was designed for arbitrary text splits where chunks lack internal coherence. Our segments are event-driven and already semantically self-contained by design. The "context loss" problem is smaller.

Neighbor retrieval is the simpler, sufficient solution: after retrieval, expand each matched segment to include segment_id ± N from the same video.

```python
def expand_with_neighbors(
    matched_segments: list[dict],
    window: int = 2
) -> list[dict]:
    expanded_ids = set()
    video_id = matched_segments[0]["payload"]["video_id"]

    for seg in matched_segments:
        seg_id = seg["payload"]["segment_id"]
        for offset in range(-window, window + 1):
            expanded_ids.add(seg_id + offset)

    # Fetch neighbors from same video
    neighbors = client.scroll(
        collection_name="video_segments",
        scroll_filter=Filter(must=[
            FieldCondition(key="video_id", match=MatchValue(value=video_id)),
            FieldCondition(key="segment_id", match=MatchAny(any=list(expanded_ids)))
        ]),
        with_payload=True,
        limit=len(expanded_ids) + 10
    )

    # Sort by segment_id to restore chronological order
    return sorted(neighbors[0], key=lambda x: x.payload["segment_id"])
```

The `prev_segment_id` and `next_segment_id` fields in the payload make this simpler to implement without a range query.

Window recommendation: ±2 segments (covers ~10-30 seconds of video context around each match). Expand to ±3 for multi-segment analyses like "describe my hook structure."

### When to Skip Neighbor Expansion

- Pure aggregation queries (Path 1): no expansion needed, just counts
- Exact keyword lookup (Path 2): the matched segment already has the phrase; expansion adds noise
- High-precision production queries where only the specific frame matters

---

## 16. Contextual Prefix Generation

### The Technique (Anthropic Contextual Retrieval, September 2024)

Before embedding a segment's transcript, prepend an LLM-generated context sentence that situates the chunk within the video as a whole. This prevents the "lost context" problem where isolated chunks have pronouns ("he", "this"), implicit references, or continuation language that is meaningless in isolation.

### Evidence

- Contextual embeddings alone: 35% reduction in retrieval failure rate (5.7% → 3.7%)
- Contextual embeddings + contextual BM25: 49% reduction (5.7% → 2.9%)
- Adding reranking on top of contextual: 67% reduction (5.7% → 1.9%)
- Cost with Anthropic prompt caching: ~$1.02 per million document tokens

### Implementation with Prompt Caching

The expensive part is sending the full video context to the LLM for each segment. Prompt caching makes this cheap: the full video JSON is cached, and only the per-segment instruction changes per call.

```python
CONTEXT_SYSTEM_PROMPT = """
You are given a complete video transcription as structured JSON.
For each segment provided, write ONE short factual sentence (under 20 words)
that situates this segment within the video as a whole.
State what the video is about and what this segment specifically covers.
Do NOT analyze or interpret. Observable facts only.
"""

def generate_context_prefix(segment: dict, video_meta: dict, full_video_json: str) -> str:
    response = gemini.generate(
        system=CONTEXT_SYSTEM_PROMPT,
        # full_video_json is sent as cached content — only charged once per video
        cached_content=full_video_json,
        prompt=f"Write the context sentence for segment {segment['segment_id']} "
               f"(timecode {segment['timecode_start']} to {segment['timecode_end']}): "
               f"{json.dumps(segment)}"
    )
    return response.text
```

Example output for segment 47 of a "camera settings" tutorial:
> "Segment 47 of a YouTube tutorial on low-light camera settings, where the creator demonstrates ISO adjustment on a DSLR."

This prefix is prepended to the transcript before embedding:
```
"Segment 47 of a YouTube tutorial on low-light camera settings, where the creator demonstrates ISO adjustment on a DSLR. I boosted the ISO to 3200 and here's what happened to the noise level."
```

### When to Skip

If Gemini API cost at ingestion is a concern and you want a free alternative: use late chunking (pass all segments for one video through the embedding model in one batch, pool per segment after forward pass). This preserves cross-segment attention without any LLM call. Requires a long-context embedding model.

---

## 17. MMR Diversification

Maximal Marginal Relevance (MMR) removes near-duplicate segments before reranking. Without it, the reranker receives 5 segments from the same 8-second window (because the creator said something relevant there) and returns all 5 — wasting 5 of the 10 context slots the LLM receives.

MMR selects candidates that are both relevant (high similarity to query) and diverse (low similarity to already-selected candidates). The tradeoff is controlled by λ:
- λ=1.0: pure relevance (same as no MMR)
- λ=0.0: pure diversity
- λ=0.7: recommended starting point (70% relevance weight, 30% diversity)

```python
import numpy as np

def mmr(
    query_vec: list[float],
    candidate_vecs: list[list[float]],
    candidates: list[dict],
    top_k: int = 30,
    lambda_: float = 0.7
) -> list[dict]:
    selected = []
    selected_vecs = []
    remaining = list(zip(candidates, candidate_vecs))

    while len(selected) < top_k and remaining:
        scores = []
        for cand, vec in remaining:
            relevance = np.dot(query_vec, vec)
            if selected_vecs:
                max_sim = max(np.dot(vec, sel_vec) for sel_vec in selected_vecs)
            else:
                max_sim = 0.0
            mmr_score = lambda_ * relevance - (1 - lambda_) * max_sim
            scores.append(mmr_score)

        best_idx = np.argmax(scores)
        best_cand, best_vec = remaining.pop(best_idx)
        selected.append(best_cand)
        selected_vecs.append(best_vec)

    return selected
```

LangChain's `QdrantVectorStore.max_marginal_relevance_search()` wraps this for convenience but doesn't integrate cleanly with hybrid search. Implement MMR client-side on the hybrid search results.

---

## 18. Creator Query Taxonomy

### Query Distribution

| Path | % of Queries | Latency | Determinism |
|---|---|---|---|
| Metadata aggregate | ~25% | <50ms | 100% deterministic |
| BM25 keyword | ~20% | <100ms | 100% deterministic |
| Semantic (single-hop) | ~35% | 200-500ms | Probabilistic |
| Cross-video comparison | ~20% | 500ms-2s | Hybrid |

### Pure Metadata Filter Queries (no vector search needed)

| Creator query | Fields used | Operation |
|---|---|---|
| "How many jump cuts in my video?" | cut_type == "jump-cut" | COUNT |
| "Total B-roll time?" | shot_type == "B-roll" | SUM duration_seconds |
| "How many segments have on-screen text?" | on_screen_text_present == true | COUNT |
| "How many wide shots do I use?" | shot_type == "WS" | COUNT |
| "How many segments have background music?" | music_present == true | COUNT |
| "What is my average segment duration?" | all segments for video_id | AVG duration_seconds |
| "Does any segment use a speed ramp?" | speed_change != "none" | EXISTS |
| "What's my most common shot type?" | all shot_type values | GROUP_BY shot_type |
| "How many unique speakers?" | speaker_id | DISTINCT COUNT |
| "Which segments have no speech?" | transcript == "" | FILTER |

### BM25 Keyword Queries (exact phrase in text fields)

| Creator query | Target field |
|---|---|
| "When did I say 'mistake'?" | speech.transcript |
| "Find every segment I mentioned my channel name" | speech.transcript |
| "Show all on-screen text with 'link in bio'" | on_screen_text.entries[].text |
| "Did competitor say 'limited time offer'?" | speech.transcript |
| "Find segments with the word 'sponsored'" | speech.transcript |
| "What does on-screen text say at 2:15?" | on_screen_text + timecode filter |

### Semantic Queries (dense vector, meaning-based)

| Creator query | Which vector | Why semantic |
|---|---|---|
| "When does my energy feel low?" | dense_transcript | Energy = inferred from delivery, not a keyword |
| "Find emotional tension moments" | dense_transcript | Emotional arc = semantic concept |
| "When am I reading from a script?" | dense_transcript | Scripted delivery = semantic quality |
| "Where is the hook weakest?" | dense_transcript | Hook weakness = structural/content concept |
| "Find the most authentic moments" | dense_transcript | Authenticity = semantic concept |
| "Find strong CTA moments" | dense_transcript | CTAs vary in phrasing — semantic needed |
| "Find my most cinematic moments" | dense_production | Cinematic = production signals, not speech |
| "Segments with the most professional look" | dense_production | Professional = lighting + composition + grade |
| "Where does background feel distracting?" | dense_production | Background perception = semantic |
| "Find high-energy editing sections" | dense_production | Energy = cut frequency + speed changes + music |

### Revenue-Connected Queries (Highest Creator Value)

| Query type | Revenue connection | Urgency |
|---|---|---|
| Hook effectiveness diagnosis | Views + algorithm distribution — YouTube penalizes early drop-off | Highest |
| Watch time / pacing analysis | Ad revenue — more watch time = more mid-roll impressions | High |
| Sponsorship segment timing | Brand conversion rate — placement at peak retention = premium rates | High |
| Production quality benchmarking | Brand deal CPM — brands pay 30-50% more for high-production creators | High |
| On-screen text / mute-watchability | TikTok/Reels completion rate — platform reach | High |
| B-roll density vs. talking head | Retention past 2-8 minutes — where mid-roll ads trigger | Medium |
| Music energy alignment | Shares + saves → algorithmic boost | Medium |
| CTA placement clarity | Affiliate clicks, subscription conversions | Medium |
| Color grade / brand consistency | Sponsorship tier perception | Medium |

### The Sponsorship Segment Problem

The schema has no explicit `is_sponsorship` field. Sponsorship must be found semantically, then its timecode used for follow-up queries.

Two-step pattern:
1. `semantic_search` with `nl_query="creator stops main content, begins brand integration or sponsor read"` → returns timecodes
2. Use those timecodes as `timecode_start_gte_seconds` / `timecode_start_lte_seconds` filters in a follow-up `aggregate_metadata` or `keyword_search`

The agent must recognize this chaining pattern. System prompt should include an explicit example of this two-step sponsorship detection flow.

---

## 19. What Works vs What Is Hype

### What Definitively Works (High Consensus, 2024-2025)

**Hybrid search (BM25/BM42 + dense)**: The single biggest quality uplift from naive vector-only RAG. 15-30% precision improvement consistently reported. Described as "the most impactful single change" across multiple practitioner reports, RAGFlow's 2024 and 2025 reviews, and benchmarks.

**Cross-encoder reranking**: Described as "highest ROI improvement for any RAG system." 15-25% relevant-in-top-5 improvement over hybrid alone. Mandatory, not optional.

**Metadata pre-filtering before semantic search**: Every production practitioner emphasizes this. Without it, all retrieval is noisy. With structured fields like ours, filtering before semantic search dramatically reduces irrelevant candidates.

**Hierarchical chunking (parent-child)**: NVIDIA internal test showed 61% → 89% accuracy improvement. The principle is valid: search on small chunks (precise), retrieve surrounding context (useful). In our case, neighbor retrieval achieves the same goal with less complexity.

**Contextual embeddings**: Anthropic's technique. 35-49% retrieval failure rate reduction on standard document corpora. With prompt caching, cost is ~$1/million tokens. Our clean, labeled data partially mitigates the need, but the improvement is real and measurable.

**Evaluation before shipping**: Teams that used Ragas/NDCG@10 monitoring early caught silent retrieval degradation. Teams that measured only final LLM output quality shipped pipelines that degraded undetected. Build evaluation from day one.

**Query classification before retrieval**: Routing counting/aggregation queries away from semantic search entirely prevents an entire class of failures. Sending "how many jump cuts" to a semantic search is wasteful and produces worse results than a direct payload query.

### What Is Hype or Situational

**"RAG is dead / long context replaces RAG"**: False in production. Long context is 8-82x more expensive for typical knowledge-base workloads. Suffers "Lost in the Middle" degradation (LLMs ignore content in the middle of very long contexts). Cannot handle corpus updates without re-running the entire context. RAG is the correct architecture for external knowledge grounding.

**Agentic RAG for simple queries**: Adding orchestration for single-hop questions adds latency and complexity with no quality gain. Agentic patterns are only justified for multi-hop, cross-video, or decomposable queries.

**LLM-based listwise reranking**: 8-17x slower and 10-24x more expensive than cross-encoders. Cross-encoders trained discriminatively on relevance pairs outperform general LLMs even when the LLM is larger. Only justified for top-5 final synthesis, not initial candidate ranking.

**HyDE (Hypothetical Document Embeddings)**: Generates a hypothetical answer and uses it as the query embedding. Works for general knowledge retrieval where vocabulary mismatch is the main problem. Performs poorly for fact-specific or personal data retrieval (hallucination risk — the hypothetical answer may describe facts that don't exist in the corpus). Our creator data is personal and fact-specific. Skip HyDE or use with a confidence-based fallback.

**RAPTOR (recursive summarization tree)**: Impressive benchmarks (20% improvement on QuALITY dataset). Requires significant ingestion-time compute and careful tree structure maintenance. Not worth the overhead for our use case — our event-driven segments already provide a clean hierarchy.

**GraphRAG**: High overhead for building and maintaining entity-relation graphs. Strong for complex relationship queries (80% vs 50% on global comprehension). For creator analytics, relevant only if relationship queries become dominant ("Which topics does this creator always combine?"). Not worth the overhead in v1.

**ColBERT / late interaction**: Stores one vector per token instead of one per chunk. Higher accuracy than bi-encoder. But storage is 4-8x larger, and Qdrant does not natively support MaxSim for ColBERT. The standard bi-encoder + cross-encoder pipeline achieves comparable accuracy for our scale (hundreds to thousands of segments per creator). Revisit if retrieval quality plateaus.

---

## 20. Key Implementation Warnings

### Critical

**Create all payload indexes at collection creation time.** Before the first upsert. Post-hoc index creation forces a full HNSW rebuild (compute-heavy). Every field you ever want to filter on must be indexed before data goes in.

**Never use LangChain's QdrantVectorStore for the search call when you need fusion control.** Use the Qdrant Python client directly for `query_points()`. LangChain's hybrid search abstraction locks you to RRF with default parameters (k=2 instead of k=60, no weight tuning, no DBSF option, no per-prefetch filter distinction). Use LangChain for chain orchestration, LLM calls, and prompt management only.

**LangChain's SelfQueryRetriever cannot generate IN operator.** It cannot produce `shot_type IN ["CU", "ECU"]` — the `QdrantTranslator` lacks `match.any`. For multi-value categorical filters, generate the filter JSON directly via LLM structured output (tool use) and construct a raw Qdrant `models.Filter` object.

**video_id pre-filter must always be set inside each Prefetch, not only at the top-level filter.** The top-level filter in `query_points()` is applied after fusion. The Prefetch-level filter is applied before vector search within each prefetch. For true pre-filtering (the efficiency and precision gain), the filter must be in each Prefetch object.

**Do not load both NVIDIA models (embed + rerank) in VRAM simultaneously on a 4GB GPU.** Each is ~2GB in BF16. At ingestion time, load only the embed model. At query time, load only the reranker (the embed model is not needed for search — stored vectors are already computed). If you must load both simultaneously, apply INT8 quantization via bitsandbytes to reduce each to ~1GB.

### Important

**The sponsorship segment is a two-step retrieval.** First: semantic search to find timecodes where the sponsor read happens. Second: use those timecodes as range filters in a follow-up query. The agent must chain these — the system prompt must explicitly describe this pattern with an example.

**Cross-video comparison is not a single RAG call.** Issue per-video sub-queries independently, collect results, synthesize with LLM. Mixing all video segments into one search and asking for comparison produces biased results (videos with more matching segments dominate).

**BM42 sparse model runs on CPU.** FastEmbed runs the BM42 model (a small transformer) on CPU. This is fine — BM42 is lightweight and is only invoked at ingestion time and at query time for query encoding. The reranker runs on GPU. The embedding model runs on GPU. BM42 on CPU is not a bottleneck.

**Payload index type must match the filter type exactly.** `video_id` must be a `KEYWORD` index, not `TEXT`. Booleans must be `BOOL` indexes. Float timecodes must be `FLOAT` indexes. Type mismatches cause silent filter failures (Qdrant returns all points when a filter condition cannot be evaluated against the wrong index type).

**MMR must be implemented client-side.** Qdrant does not have a native MMR step. LangChain's `max_marginal_relevance_search` abstracts this but doesn't integrate cleanly with multi-vector hybrid search. Implement MMR client-side on the raw hybrid search result list before passing to the reranker.

**The dense_production vector is meaningless for segments with no production signal** (e.g., screen-recording segments where all frame/lighting/camera fields are "N/A"). For such segments, either skip generating `dense_production` (use a zero vector) or embed a placeholder. The agent should never route to `dense_production` for queries where the user is clearly asking about what was said.

---

## 21. Build Priority Order

| Priority | Task | Dependency | Expected Value |
|---|---|---|---|
| 1 | Qdrant collection creation with named vectors + ALL payload indexes | Nothing | Foundation for everything |
| 2 | Ingestion pipeline: dense_transcript vector + BM42 sparse | Collection | MVP retrieval |
| 3 | Path 1 (aggregate) and Path 2 (keyword) retrieval | Ingestion | Highest creator trust — deterministic, always correct |
| 4 | Path 3 semantic search (dense_transcript only) + video_id pre-filter | Ingestion | Core product value |
| 5 | Query classifier (LLM tool use, routes to correct path) | Paths 1-3 | Makes it a real chat product |
| 6 | NVIDIA reranker integration | Path 3 | 15-25% quality improvement |
| 7 | MMR diversification before reranking | Reranker | Eliminates duplicate context |
| 8 | dense_production vector generation + routing logic | Ingestion, classifier | Unlocks visual/style/production queries |
| 9 | Neighbor expansion on retrieval | Paths 2-3 | Better LLM response quality |
| 10 | Contextual prefix generation (Gemini, prompt caching) | Ingestion | 35-49% retrieval failure reduction |
| 11 | Path 4 cross-video comparison orchestration | Classifier, Paths 1-3 | Highest-value creator feature |
| 12 | Evaluation framework (Ragas / NDCG@10 monitoring) | Running system | Catch silent degradation |
| 13 | Fusion parameter tuning (RRF k, weights) | Evaluation data | Marginal quality improvement |
| 14 | INT8 quantization for simultaneous model loading | Both models | Quality of life / memory optimization |

---

## 22. NVIDIA Model Alternatives Considered

### Why These Were Ruled Out

| Model | VRAM Required | Why Ruled Out |
|---|---|---|
| `nvidia/NV-Embed-v2` | 24-48GB | OOM on RTX 4090 24GB. ~15GB disk. Community reports: exhausts 4090 before completing inference on a 6-page PDF. No GGUF quantized version (conversion fails due to custom MistralModel code). CC-BY-NC-4.0 (non-commercial). |
| `nvidia/llama-embed-nemotron-8b` | ~80GB | Requires A100 or H100. Flash-attn 2.6.3 hard dependency. Non-commercial license. |
| `nvidia/llama-3.2-nv-rerankqa-1b-v2` | ~2GB | Predecessor to llama-nemotron-rerank-1b-v2. Superseded. No reason to use on new project. |
| Cohere Rerank 4 Pro | — | Paid API. User policy: only Gemini as paid API. |
| `jinaai/jina-reranker-v2-base-multilingual` | CPU-feasible | CC-BY-NC-4.0 — non-commercial only. |

### Quantization Path (If 4GB Becomes Tight)

If both NVIDIA models need to be loaded simultaneously (e.g., for a streaming pipeline where embed and rerank happen in the same request handler):

```python
from transformers import BitsAndBytesConfig

quant_config = BitsAndBytesConfig(load_in_8bit=True)
# Reduces ~2GB BF16 model to ~1GB INT8
# Both models together: ~2GB total — comfortable in 4GB VRAM
```

INT8 quantization has minimal impact on reranking accuracy (cross-encoders are robust to 8-bit quantization). Embedding models show slightly more sensitivity — test on a held-out segment sample before committing.

### No GGUF Versions Available

As of May 2025, no GGUF, AWQ, or GPTQ quantized versions of any NVIDIA embedding or reranking models exist on HuggingFace. Conversion of NV-Embed-v2 fails due to custom model code incompatible with standard `llama.cpp` conversion scripts. The 1B models (llama-nemotron-embed-1b-v2 and llama-nemotron-rerank-1b-v2) are Llama-3.2-1B based so GGUF conversion is theoretically possible but no published version exists. Use bitsandbytes INT8 as the quantization path instead.

---

*Research conducted: May 2026. Sources: HuggingFace model cards, Qdrant documentation and research articles, LangChain documentation and GitHub issues, Anthropic contextual retrieval publication (September 2024), RAGFlow 2024/2025 reviews, ZeroEntropy reranking benchmarks, practitioner reports from Reddit r/LocalLLaMA and r/MachineLearning, AI Engineer World's Fair 2024/2025, arXiv papers (2406.13213, 2512.05411, 2409.04701, 2401.18059, 2501.09136), creator community research from RetentionRabbit, AIR Media-Tech, CreatorGrid, VidIQ ecosystem.*
