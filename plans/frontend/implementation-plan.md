# CreatorJoy Frontend — Implementation Plan

## Context
The backend (ingestion, transcription, RAG, chat) is fully implemented. The `frontend/` directory is empty. This plan covers every step to build the React single-page app that connects to the existing FastAPI backend. Design spec: `docs/frontend-design.md`.

---

## Step 1 — Fix Backend Gaps (do these FIRST, verify with curl before touching frontend)

Five small additions to `backend/` are required.

### 1a — `GET /projects` — list all projects
- **File:** `backend/api/routers/projects.py`
- Add a route that calls `db.list_projects()` — this method already exists in `backend/creator_joy/ingestion/database.py`
- Needed by: Projects Dashboard page

### 1b — Static file serving for thumbnails and videos
- **File:** `backend/api/main.py`
- After all router includes: `app.mount("/downloads", StaticFiles(directory="downloads"), name="downloads")`
- Import: `from fastapi.staticfiles import StaticFiles` (Starlette already installed, no new package)
- Thumbnail URL: `/downloads/projects/{project_id}/videos/{video_id}/source_video.webp`
- Video URL: `/downloads/projects/{project_id}/videos/{video_id}/source_video.mp4`

### 1c — `POST /projects/{id}/videos/{vid}/transcribe`
- **File:** `backend/api/routers/ingestion.py`
- Calls `TranscriptionService().transcribe_video(video_id)` from `backend/creator_joy/transcription/service.py`
- This call is blocking (Gemini takes 2–10 min). Acceptable for MVP.

### 1d — `POST /projects/{id}/videos/{vid}/index`
- **File:** `backend/api/routers/ingestion.py`
- Calls `RAGService().index_video(video_id)` from `backend/creator_joy/rag/service.py`
- Also blocking. Return `{status, segments_indexed}` from the IndexRecord.

### 1e — `GET /projects/{id}/chat/sessions` — list sessions
- **File:** `backend/creator_joy/chat/memory.py` — add `list_sessions(project_id)` method querying `chat_history` grouped by `session_id`, returning `{session_id, first_message, last_active}`
- **File:** `backend/api/routers/chat.py` — add GET route calling that method

---

## Step 2 — Initialize the Frontend Project

Run from inside `frontend/`:

```
npm create vite@latest . -- --template react
npm install
npm install lucide-react clsx uuid
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

**Do NOT install React Router.** All navigation is pure React state — no URL changes ever.

### Tailwind — custom color tokens in `tailwind.config.js`

| Token | Hex | Used for |
|---|---|---|
| `bg` | `#020617` | Page background |
| `surface` | `#0f172a` | Cards, sidebar |
| `border` | `#1e293b` | Dividers |
| `primary` | `#0ea5e9` | Buttons, active states |
| `primary-hover` | `#38bdf8` | Hover glow |
| `accent` | `#ac4bff` | Competitor video labels |
| `success` | `#00c758` | Completion indicators |
| `muted` | `#7dd3fc` | Secondary text, timestamps |

Fonts: **Inter** (body) + **Plus Jakarta Sans** (headings) — add via Google Fonts link in `index.html`.

### Vite proxy in `vite.config.js` (dev only)
- `/api` → `http://localhost:8000` (strip `/api` prefix)
- `/downloads` → `http://localhost:8000` (no rewrite)

---

## Step 3 — Folder and File Structure

Create this exact structure under `frontend/src/`:

```
frontend/src/
├── main.jsx
├── App.jsx                         ← activeView + activeProject state lives here
├── index.css                       ← Tailwind directives + Google Fonts import
│
├── api/
│   ├── projects.js                 ← createProject(), listProjects(), getProject()
│   ├── videos.js                   ← listVideos(), ingestUrl(), transcribeVideo(), indexVideo()
│   └── chat.js                     ← streamChat() (fetch+ReadableStream), getHistory(), listSessions()
│
├── hooks/
│   ├── useProjects.js              ← projects list + createProject action
│   ├── useVideos.js                ← videos list + pendingIngestions local state
│   ├── useChat.js                  ← messages, streaming, skillLog
│   └── useSessions.js             ← sessions (backend + localStorage merged)
│
├── utils/
│   ├── sessionStorage.js           ← getSessions / saveSession / removeSession (localStorage)
│   ├── parseEngagement.js          ← JSON.parse engagement_metrics safely, null-safe formatters
│   ├── formatDate.js               ← "yesterday", "3 days ago" relative timestamps
│   └── mediaUrls.js                ← thumbnailUrl(projectId, videoId), videoUrl(...)
│
└── components/
    ├── layout/
    │   ├── Header.jsx              ← fixed top bar: logo + account stub
    │   └── AppShell.jsx            ← dark bg wrapper, min-h-screen
    │
    ├── dashboard/
    │   ├── ProjectsDashboard.jsx   ← project card grid + empty state
    │   ├── ProjectCard.jsx         ← card with thumbnail collage, badges, hover glow
    │   ├── ThumbnailCollage.jsx    ← 2×2 grid of up to 4 thumbnails
    │   └── NewProjectModal.jsx     ← name input + create button
    │
    ├── workspace/
    │   ├── WorkspaceLayout.jsx     ← two-panel flex layout (sidebar + chat)
    │   ├── Sidebar.jsx             ← composes VideoSection + ChatSection
    │   │
    │   ├── videos/
    │   │   ├── VideoSection.jsx         ← header + url input + card list
    │   │   ├── UrlInputBar.jsx          ← url field + role toggle (creator/competitor) + send
    │   │   ├── VideoCard.jsx            ← state machine: thumbnail | playing | metrics
    │   │   ├── VideoPlayer.jsx          ← <video> element, same card dimensions (inline)
    │   │   ├── EngagementPanel.jsx      ← metrics flip view with back button
    │   │   ├── IngestionProgress.jsx    ← pulsing placeholder + 3-step stage indicators
    │   │   └── RoleBadge.jsx            ← "Creator" sky blue / "Competitor" purple pill
    │   │
    │   └── chat/
    │       ├── ChatSection.jsx          ← session list + header
    │       ├── SessionItem.jsx          ← session row, active left border
    │       ├── ChatArea.jsx             ← breadcrumb + message thread + input
    │       ├── MessageThread.jsx        ← scrollable list, auto-scroll to bottom
    │       ├── UserMessage.jsx          ← right-aligned sky blue bubble
    │       ├── AiMessage.jsx            ← left-aligned dark card, streaming cursor blink
    │       ├── SkillActivityLog.jsx     ← inline skill event lines (NOT chat bubbles)
    │       └── ChatInput.jsx            ← textarea + send, disabled while streaming
    │
    └── ui/
        ├── Modal.jsx
        ├── Spinner.jsx
        ├── Badge.jsx
        └── Button.jsx
```

---

## Step 4 — State Architecture

No Redux, no Zustand. Plain `useState` + `useReducer` at the appropriate level.

### `App.jsx` owns (passed down as props)
- `activeView: 'dashboard' | 'workspace'`
- `activeProject: ProjectRecord | null`

### `useProjects` — used in ProjectsDashboard
- `projects`, `loading`, `error`
- Fetches `GET /api/projects` on mount
- `createProject(name)` → POST → returns new project object

### `useVideos` — scoped to active project
- `videos: ParsedVideoRecord[]` — `engagement_metrics` already JSON.parsed here
- `pendingIngestions: IngestingVideo[]` — local-only state for in-flight pipeline cards
- Fetches `GET /api/projects/{id}/videos` on mount

### `useSessions` — used in Sidebar + ChatArea
- `sessions: SessionMeta[]` — merged from backend + localStorage
- `activeSessionId: string | null`
- `createSession()` — `crypto.randomUUID()` → localStorage → set active
- `activateSession(id)` — switches session, triggers history load

### `useChat` — scoped to project + session
- `messages`, `streaming`, `currentStreamText`, `skillLog`
- On `activeSessionId` change: loads `GET /api/.../sessions/{sid}/history`
- `sendMessage(text)` — drives SSE stream

### Component-local state (not shared)
- `VideoCard`: `mode: 'thumbnail' | 'playing' | 'metrics'`
- `VideoSection`: `showUrlInput: boolean`
- `NewProjectModal`: `projectName`, `open`
- `IngestionProgress`: `stage: 'downloading' | 'transcribing' | 'indexing' | 'done' | 'error'`

---

## Step 5 — Session Management (localStorage)

Sessions with no messages only exist in localStorage. Sessions with messages exist in both.

**localStorage key pattern:** `creatorjoy:sessions:{project_id}`
**Stored value:** JSON array of `{id, label, created_at, project_id}`

### Merge logic in `useSessions`
1. Fetch `GET /api/projects/{id}/chat/sessions` — sessions with real messages (has `first_message`, `last_active`)
2. Read localStorage for same project
3. Merge by `session_id` — backend is authoritative; localStorage fills in unused sessions
4. Sort by `last_active` descending

### On `+ New Chat`
`crypto.randomUUID()` → save to localStorage → set as `activeSessionId` → clear messages

---

## Step 6 — Build Order (each step testable before the next)

1. **Backend gaps** — fix all 5, verify with curl
2. **Vite + Tailwind + fonts** — confirm dark background `#020617` renders, fonts load
3. **`api/` functions** — test in browser console that fetch calls succeed against the proxy
4. **`AppShell` + `Header`** — layout skeleton confirms, logo visible
5. **`ProjectsDashboard` + `ProjectCard`** — with hardcoded fake data first, confirm grid + hover
6. **`useProjects` wired** — real API data, `+ New Project` modal, POST, navigate to workspace
7. **`WorkspaceLayout`** — two-panel confirmed at various window sizes, sidebar is fixed-width
8. **`VideoSection` + `UrlInputBar` + `VideoCard`** — hardcoded fake data, confirm layout
9. **`useVideos` wired** — real API data, `engagement_metrics` JSON.parsed, cards render
10. **`IngestionProgress` + 3-stage pipeline** — URL submit → all three API calls → thumbnail appears
11. **`VideoCard` interactions** — inline playback, engagement flip, role badge colors
12. **`ChatSection` + `useSessions`** — session list renders, `+ New Chat` creates session
13. **`ChatArea` + history load** — historical messages render correctly
14. **SSE streaming** — `sendMessage` drives stream, tokens appear character-by-character, skill log updates live
15. **Polish** — empty states, error states, scroll-to-bottom, timestamps, breadcrumb

---

## Step 7 — Three-Stage Ingestion Flow (detail)

After user submits a URL:

1. Immediately add `pendingIngestion` to local state → `IngestionProgress` card renders with pulsing animation
2. `POST /api/projects/{id}/ingest` `{urls: [url], roles: [role]}` — await (blocking, 10–60s)
   - Success: get `video.id`, advance stage to `'transcribing'`
   - Error: set `stage: 'error'`
3. `POST /api/projects/{id}/videos/{vid}/transcribe` — await (blocking, 2–10 min)
   - Success: advance stage to `'indexing'`
4. `POST /api/projects/{id}/videos/{vid}/index` — await (blocking, 1–5 min)
   - Success: advance stage to `'done'`
5. Refresh video list via `GET /api/projects/{id}/videos` → real `VideoCard` appears → remove `pendingIngestion`

**Progress card visual:**
```
✓ Downloading    ← green checkmark when done
⟳ Transcribing  ← active spinner
○ Indexing       ← gray, not yet started
```

**Do NOT use `AbortSignal` with a short timeout** — these fetches are intentionally long-running.

---

## Step 8 — SSE Stream Handling

The chat endpoint is `POST`, not `GET`. **Do NOT use the browser's native `EventSource`** — it only supports GET. Use `fetch` with manual `ReadableStream` reading.

### Pattern in `api/chat.js`
```
fetch POST
→ response.body.getReader()
→ read() loop
→ TextDecoder
→ buffer + split on '\n\n'
→ parse lines starting with 'data: '
→ JSON.parse
→ call onEvent(event)
```

### Event handling in `useChat.sendMessage`
| Event type | Action |
|---|---|
| `token` | Append `event.content` to a `useRef` accumulator AND `useState` (ref for the `done` handler, state for rendering) |
| `skill_start` | Push `{skill, status: 'active'}` to `skillLog` |
| `skill_complete` | Update matching entry in `skillLog` to `status: 'complete'` |
| `skill_error` | Update matching entry to `status: 'error'` |
| `done` | Move ref accumulator into `messages` array (with attached `skillLog`), reset all stream state |

**Auto-scroll:** `useRef` pointing to a div at the bottom of the message list. `useEffect` calls `ref.current.scrollIntoView({behavior:'smooth'})` whenever `currentStreamText` or `messages` changes.

**Input disabled** while `streaming === true`.

---

## Step 9 — Critical Gotchas

| # | What will break | How to fix |
|---|---|---|
| 1 | `engagement_metrics` is a JSON **string**, not an object | Always: `video.engagement_metrics ? JSON.parse(video.engagement_metrics) : {}` — do this in `parseEngagement.js` |
| 2 | Session IDs are **frontend-generated** | `crypto.randomUUID()` on `+ New Chat` click, NOT on first message send |
| 3 | Chat SSE endpoint is **POST** | Use `fetch` + `ReadableStream` — NEVER `EventSource` |
| 4 | Ingest/transcribe/index are **blocking HTTP calls** | No short `AbortSignal` timeout — just await them |
| 5 | `VideoRecord.status` only tracks download | Track transcription/index stages in local `pendingIngestions` state — do NOT poll backend for these |
| 6 | Thumbnail filename is **always `source_video.webp`** | Never derive from title or ID. Add `.jpg` `onError` fallback |
| 7 | `ingest` body **must use arrays** even for 1 video | `{urls: [url], roles: [role]}` |
| 8 | `list_projects` returns **oldest-first** | `projects.slice().reverse()` on the frontend |
| 9 | Every engagement metric can be **null** | Show `"—"` for null — never access a property without a null guard |
| 10 | Chat history `role` is `'user'` or `'assistant'` only | Tool call rows are filtered by backend — no special handling needed |
| 11 | **Sidebar independent scrolling** breaks without `min-h-0` | Video section: `flex-1 overflow-y-auto min-h-0`. Chat section: `flex-none h-64 overflow-y-auto` |
| 12 | `+ New Project` needs the project **ID before navigating** | Await the POST, get `id` from response, then `setActiveProject` |
| 13 | `currentStreamText` **ref vs state** | Keep a `useRef` alongside `useState` — the `done` handler reads the ref synchronously |

---

## Step 10 — End-to-End Verification Checklist

- [ ] App loads → Projects Dashboard with empty state
- [ ] Create new project → navigate to empty workspace
- [ ] Paste YouTube URL → three-stage progress → thumbnail appears
- [ ] Hover thumbnail → play button appears → click → video plays inline (same card, no popup)
- [ ] Click chart icon → engagement metrics visible → back → thumbnail returns
- [ ] Creator video badge is sky blue, competitor badge is purple
- [ ] `+ New Chat` → session created → empty chat
- [ ] Send message → skill log updates live → AI response streams token by token
- [ ] Back to Projects → project card shows thumbnail collage
- [ ] Click previous session → history loads correctly
- [ ] Question using multiple skills → all skill events appear sequentially in log

---

## Backend Files to Modify (Step 1 only)

- `backend/api/main.py` — StaticFiles mount
- `backend/api/routers/projects.py` — `GET /projects`
- `backend/api/routers/ingestion.py` — `/transcribe` and `/index` routes
- `backend/api/routers/chat.py` — `GET /projects/{id}/chat/sessions`
- `backend/creator_joy/chat/memory.py` — `list_sessions()` method

## Frontend Files to Create (Steps 2–15)

All new files under `frontend/src/` per the folder structure in Step 3. No existing backend files are modified after Step 1.
