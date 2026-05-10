# Creator-Joy

A video analysis chatbot for content creators. You drop in a YouTube URL, and CreatorJoy downloads it, runs a deep multimodal analysis using Gemini, indexes every segment into a vector database, and then lets you chat with all of it. Ask about your hook, your editing rhythm, how a competitor structures their videos, what changes between your best and worst performing content. That kind of thing.

This is a portfolio project. I built it to show how I think about product problems and how I translate that thinking into actual working systems. The code is real, the pipeline runs end to end, and every design decision in here has a reason behind it.

---

## The Product Problem That Started All of This

The obvious first idea was to use yt-dlp to pull the auto-generated captions from YouTube and use those as the data. That would have taken maybe a day to build. But then I thought about what a creator actually does when they study a video. They are not reading captions. They are watching the video, noticing how the camera moves, when the music kicks in, what text overlays are on screen, how fast the cuts are, what the lighting looks like, where the host positions themselves in the frame. The story of a video is not just in the words.

If I just indexed captions, a creator could ask "what did I say at 2:30?" but not "why does my video feel less energetic than my competitor's in the first 30 seconds?" or "how do I use text overlays differently than they do?" The captions would answer maybe 20% of the questions a creator actually cares about.

So I scrapped the caption idea entirely and decided to use Gemini, which is a multimodal model that understands both video and audio at the same time. Instead of just extracting words, I would have Gemini analyze every few seconds of video and produce a structured, field-by-field breakdown of what is actually happening in the frame. The resulting data is what I call a Rich Video Transcription.

---

## Rich Video Transcription

The transcription is not a transcript. Well, it contains one, but it is much more than that. For every 10-second segment of a video, Gemini produces a JSON object with fields covering:

- The verbatim spoken words (not paraphrased, exact)
- Shot type: MCU, wide shot, B-roll, screen recording, etc.
- Camera angle and movement: eye-level, high-angle, static, dolly-in
- Lighting: soft vs hard, key light direction, color temperature feel
- Background: studio, home-office, outdoor, blurred, plain wall
- On-screen text: every overlay, lower-third, or caption burned into the video
- Graphics and animations: whether they are present and what type
- Editing: did a cut occur, what kind (hard cut, jump cut, match cut), transition effects
- Audio: is music present, what genre feel, what tempo, is there a sound effect
- Production quality: inferred microphone type, color grade feel, audio quality assessment
- An observable summary: one factual sentence Gemini writes first, anchoring everything else before filling in the individual fields

That last one matters a lot. There is a failure mode with multimodal models where they fill in fields based on what they expect to see rather than what is actually in the frame. If the video title suggests it is a tutorial, the model might write "explains a concept clearly" for every segment even when the speaker is just looking off camera. The observable summary forces the model to commit to one concrete, factual observation first before going field by field. It dramatically reduces that kind of hallucination.

The other research-backed decision was message ordering. Video goes into the prompt before the text instructions. Reversing this causes Gemini to pay less attention to the visual content because it has already formed context from the text before seeing the frames.

And we do not use `.with_structured_output()` because it is unreliable with Gemini. Instead, the JSON schema goes directly into the prompt, the model is told to output JSON only in caps, and we have a three-step parse fallback: try direct parse, then strip backtick wrappers, then send the raw output back to the model with the parse error and ask it to fix itself. Only after all three fail do we raise.

The result is a transcription file that is probably 20 to 30 times richer than what you would get from captions alone, and it unlocks a completely different quality of questions.

---

## The RAG Pipeline

Once we have these rich transcription files, we need to be able to search across them efficiently. A creator might have 10 or 20 videos in a project. Each video might have dozens of segments. That is a lot of JSON on disk, and we can not just stuff all of it into a prompt every time someone asks a question.

The indexing layer uses Qdrant as the vector database, and each segment becomes one point in Qdrant with three vectors attached to it.

**Dense transcript vector:** This embeds the spoken words plus the observable summary using Qwen3-Embedding-0.6B. Use this when the question is about what the creator is saying or the general semantic content of a segment.

**Dense production vector:** This embeds a natural language sentence we construct from the production metadata fields. Something like "MCU shot, eye-level angle, studio background, soft lighting from front, vibrant color grade, lav microphone, upbeat-pop background music." Use this when the question is about how the video looks or feels.

**Sparse vector:** This uses miniCOIL via fastembed, which is a learned sparse model. It is smarter than BM25 because it learns which tokens actually matter in context, but it still gives you that lexical signal. Dense alone misses exact keyword matches because of embedding space compression. Sparse fills that gap.

At search time, all three vectors run as prefetch candidates and get fused together using Reciprocal Rank Fusion. Then a cross-encoder reranker (Qwen3-Reranker-0.6B) rescores the top candidates by comparing the full query against the full segment text. The reranker is what actually separates the closely ranked candidates at the end.

The whole stack (both 0.6B models together) fits in about 2.4 GB of VRAM without any quantization. I specifically chose these models over larger ones because this is a 4-layer pipeline that has to run quickly, and oversized models would make it impractical on normal hardware.

Beyond semantic search, the pipeline also supports structural queries because a lot of creator questions are not semantic at all. "How many segments use a lower-third" is a boolean filter on a payload field. "What is my shot type distribution across the video" is a GROUP_BY aggregation. "How much total time does music play in this video" is a SUM operation. These go through Qdrant's scroll and count APIs directly and bypass the embedding models entirely. Structural queries are deterministic and fast. We only use semantic search when the question genuinely cannot be expressed as field values.

The search tool the LLM uses has three modes. Mode 1 is structural only. Mode 2 is semantic only. Mode 3 is hybrid where structural filters narrow the candidate set first and then semantic search runs on that subset. The mode is inferred automatically from which arguments are provided, so the LLM does not have to think about it explicitly.

---

## The Skill-Based Chat Agent

Most chatbot systems built with LangGraph end up as a single agent with many tools, or as a rigid multi-agent pipeline where each agent has a fixed role. I did not want either of those.

The single-agent-many-tools approach falls apart because the more tools you give a model, the more it has to reason about which one to call and how to call it correctly. With something like Gemini, weird edge cases start showing up around tool call schemas, argument validation, and concurrent tool behavior. The more tools, the more surface area for failure.

The fixed multi-agent pipeline approach is too rigid. If someone asks "compare my editing style to my competitor's," a fixed pipeline would need a predetermined route through a specific set of agents. But if the question is about something slightly different, the whole routing breaks down.

What I built instead is a skill-based architecture. There is one orchestrator agent that has exactly one tool: `use_sub_agent_with_skill`. The orchestrator's only job is to figure out which skill to delegate to and write a detailed briefing for that delegation. Each skill is a dynamically assembled sub-agent that gets spun up fresh for each call with exactly the tools and context it needs for that specific skill, nothing else.

The orchestrator writes a situational prompt when it delegates. Not just "analyze the hook." It has to write what the user goal is, what prior findings exist from earlier sub-agent calls in this turn, what specifically to do right now, which video UUIDs are in scope, and why this particular skill is being called. This forces the orchestrator to think before delegating rather than just firing off tool calls.

There are 14 skills in total. A few of the ones worth mentioning:

**HookDiagnosis:** Analyzes the first 30 seconds. Instead of giving this skill a retrieval tool, we pre-fetch the first 30 seconds of segments directly and inject them into the human message before the agent even starts. The agent gets all the data it needs and has no tools. This is more deterministic and faster because the retrieval scope is fully known ahead of time.

**TwoVideoComparison:** Retrieves the same fields from two videos and returns a side-by-side comparison. It is explicitly instructed never to compare asymmetrically.

**RetentionDiagnosis:** For when you know a retention drop happened at a specific timecode and you want to know what was happening in the video at that moment.

**OverlayAudit:** Returns a complete chronological inventory of every text overlay in the video. Like HookDiagnosis, this one pre-fetches all segments and injects them rather than giving the agent a retrieval tool, because the scope is the entire video and completeness matters.

**search_skill:** The retrieval layer. This is what dynamic skills call internally via a `retrieve` tool when they need data. It is the only skill that touches Qdrant directly. Specialized skills write plain English descriptions of what they need, and search_skill handles all the filter syntax, mode selection, and field names. This is the separation that prevents hallucination in skill agents: they never have to know that shot_type or camera_angle is the right field name, they just ask for what they need.

---

## Memory and Conversation History

Conversation history is stored in SQLite alongside the ingestion and transcription data. What gets stored is important: only the final user messages and the final synthesized assistant responses. Not raw Qdrant payloads. Not sub-agent internal reasoning. Not intermediate retrieval results.

The reason is context window management. If we stored raw Qdrant payloads in history, a conversation of 10 turns could easily blow up to 50,000 tokens just in the history, before we even add the current message. Synthesized responses are maybe 200 to 500 tokens each. That is a manageable history that actually helps the orchestrator understand prior conversation context without drowning in old data.

There is also automatic compaction. If a session exceeds a threshold number of turns, the oldest turns get summarized into a single assistant message, keeping the most recent turns intact. This keeps long sessions functional.

---

## Frontend

The frontend is a React app with a workspace layout. Left sidebar has project navigation and chat session management. Main area has a videos panel where you can see thumbnails, play videos, view engagement metrics per video, and retry failed pipeline steps. Chat panel on the right where you can start new sessions and see the history.

The chat streaming uses Server-Sent Events. When the orchestrator delegates to a skill, the frontend shows a spinner with the skill name. When the skill completes, it becomes a checkmark. Then the final synthesized response streams in token by token. The skill activity log stays attached to the message after streaming completes so you can see what was used to answer any question.

---

## How to Run

### Prerequisites

- Python 3.12
- Node.js 18 or later
- Docker (for Qdrant)
- A Google AI API key (Gemini)

### Backend

```bash
cd backend

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
```

Now open `.env` and fill in your values:

```
GOOGLE_API_KEY=your_google_ai_key_here
GEMINI_MODEL=gemini-2.5-flash-preview-05-20

LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_key_here_or_leave_blank
LANGCHAIN_PROJECT=creator-joy

QDRANT_HOST=localhost
QDRANT_PORT=6333

VIDEO_MAX_HEIGHT=720
HF_HUB_OFFLINE=1
```

Export all environment variables:

```bash
export $(grep -v '^#' .env | xargs)
```

Start Qdrant:

```bash
docker run -p 6333:6333 qdrant/qdrant:v1.17.1
```

Start the backend:

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be running at `http://localhost:8000`. You can check it at `http://localhost:8000/` which should return a welcome message.

### Frontend

```bash
cd frontend

npm install

npm run dev
```

The frontend runs at `http://localhost:5173` and proxies API calls to the backend at port 8000.

### Using It

1. Open the app in your browser
2. Create a new project from the left sidebar
3. In the Videos panel, paste in a YouTube URL and set the role (your video or a competitor video)
4. Wait for the pipeline: download, transcription (this takes a few minutes, Gemini is doing a lot), then indexing
5. Start a chat session and ask questions about the video

The pipeline status updates in the video card while it runs. If something fails partway through, there is a retry button on the video card that picks up from where it left off rather than starting over.

---

## Tech Stack

| Layer | What |
|---|---|
| Video download | yt-dlp |
| Transcription | Gemini (multimodal), google-genai, langchain-google-genai |
| Vector database | Qdrant 1.17.1 |
| Dense embeddings | Qwen3-Embedding-0.6B via sentence-transformers |
| Sparse embeddings | miniCOIL-v1 via fastembed |
| Reranker | Qwen3-Reranker-0.6B via sentence-transformers CrossEncoder |
| Orchestrator LLM | Gemini 2.5 Flash |
| Agent framework | LangGraph, LangChain |
| Backend | FastAPI, uvicorn |
| Persistence | SQLite |
| Frontend | React, Vite, Tailwind CSS |

---

## Docs and Plans

The `plans/` folder has detailed implementation plans for every component: the transcription pipeline, the RAG architecture, the chatbot, and all 14 skill files. The design decisions in those documents are much more detailed than what I summarized above. If you want to understand exactly why a particular thing was built the way it was, that is the place to look.
