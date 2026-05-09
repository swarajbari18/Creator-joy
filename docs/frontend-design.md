# CreatorJoy Frontend — UI/UX Design Document

## Overview

CreatorJoy is a video analytics chatbot for content creators. The frontend is a **single-page React app** — the URL in the browser never changes, no page reloads ever happen. Clicking on projects, switching chats, adding videos — everything just swaps what's shown on screen through React state.

---

## Color Palette (sourced from creatorjoy.com)

| Role | Hex | Used For |
|---|---|---|
| Page background | `#020617` | Entire app background |
| Card/surface | `#0f172a` | Sidebar, cards, chat bubbles |
| Borders/dividers | `#1e293b` | Subtle separators |
| Primary brand (sky blue) | `#0ea5e9` | Buttons, active states, highlights |
| Primary hover | `#38bdf8` | Glow, hover states |
| Accent purple | `#ac4bff` | Competitor video labels |
| Success green | `#00c758` | Completed states, success indicators |
| Primary text | `#ffffff` | Headings, body text |
| Muted text | `#7dd3fc` | Timestamps, secondary labels |

**Fonts:** Inter (body text), Plus Jakarta Sans (headings)

---

## Page 1 — Home / Projects Dashboard

The first page a user sees. Shows all their projects.

### Layout
- Fixed top header bar: CreatorJoy logo on the left, user account button on the right
- Page title "Your Projects" with a `+ New Project` button in sky blue top right
- Grid of project cards below (2–3 columns)

### Project Card
Each card represents one project:
- Dark card background (`#0f172a`) with heavily rounded corners
- Subtle sky blue border that glows brighter on hover
- A tiled collage of the first 3–4 video thumbnails from the project with rounded edges
- Project name in white bold text below the collage
- Two small badges: "X videos" and "X chats"
- Muted timestamp: "Last active X days ago"
- On hover: card lifts slightly (subtle shadow + scale effect), border glows

### Empty State
If the user has no projects: centered message with a "Create your first project" button.

### Creating a New Project
Clicking `+ New Project` opens a simple modal (a small popup):
- One input field: project name
- A create button
- On create: user is immediately taken to the empty project workspace

---

## Page 2 — Project Workspace

The main app screen. **Two-panel layout**: left sidebar (fixed, ~280px wide) + right chat area (fills remaining width).

---

## Left Sidebar

Split into two vertical sections: **Videos (top)** and **Chats (bottom)**.

---

### Videos Section (top of sidebar)

**Header row:** "Videos" label on the left. A small `+` button on the right to add a video.

**Adding a video:**
When `+` is clicked, a URL input box appears — a text field with an arrow/send button. The user pastes any URL (YouTube, TikTok, Instagram, etc. — all supported via yt-dlp) and presses enter or clicks the arrow.

**Ingestion pipeline — three visible stages:**
After the URL is submitted, a placeholder card appears in the video list with a pulsing animation. Below the placeholder, a small status label cycles through three steps:

1. **Downloading** — yt-dlp fetches the video, audio, thumbnail, metadata
2. **Transcribing** — Gemini multimodal AI analyzes the video and creates the rich segment data
3. **Indexing** — segments are loaded into the vector database (Qdrant) for retrieval

Each step shows as the active stage with a spinner. Completed steps show a green checkmark. Once all three complete, the thumbnail fades in and the video is ready to chat about.

This requires three sequential API calls from the frontend:
- `POST /projects/{id}/ingest` → wait for completion
- `POST /projects/{id}/videos/{vid}/transcribe` → wait for completion
- `POST /projects/{id}/videos/{vid}/index` → wait for completion

**Each video card in the sidebar:**
- A 16:9 thumbnail image with rounded edges
- Video title below, truncated to one line
- A role badge in the top-left corner of the thumbnail:
  - "Creator" in sky blue (`#0ea5e9`) — the user's own videos
  - "Competitor" in purple (`#ac4bff`) — competitor videos
- A small bar chart icon in the bottom-right corner of the thumbnail (always visible, semi-transparent)

**Hover interaction (inline playback):**
When the mouse hovers over a thumbnail, a white semi-transparent play button icon fades in at the center. Clicking it turns the thumbnail into a video player right in place — the image is replaced by a `<video>` element in the same card, with standard play/pause/volume controls at the bottom. The video plays locally from the downloaded file. Clicking pause or navigating away returns to the thumbnail. This is called **inline playback** — no popup, no overlay, no floating window.

**Engagement metrics interaction:**
Clicking the bar chart icon on a thumbnail smoothly fades/transitions that card to show the pre-computed engagement data:
- View count, like count, comment count
- ER (engagement rate, views-based): X.XX%
- Benchmark tier (micro, mid, macro)
- Assessment label (below average / average / good / excellent)
- Duration, days since upload
- Heatmap peak intensity (if available)
A small back arrow returns to the thumbnail view.

The videos section scrolls independently if there are many videos.

---

### Chats Section (bottom of sidebar)

A horizontal divider separates it from the videos section.

**Header row:** "Chats" label on the left. `+ New Chat` button in sky blue on the right.

**Session list:**
Previous chat sessions for this project, each showing:
- The first few words of the opening message (so the user can recognize it)
- A muted timestamp (e.g., "yesterday", "May 8")
- Active session has a sky blue left border and a slightly lighter background

Clicking a session loads that conversation in the main chat area. Sessions scroll if there are many.

---

## Right Side — Main Chat Area

### Top bar (fixed)
Breadcrumb: project name → current session name (or "New Chat").

### Message thread (scrollable)
- **User messages:** right-aligned, sky blue bubble
- **AI messages:** left-aligned, dark card (`#1e293b`), white text, rounded corners
- **Skill activity log:** appears between the user message and the AI response while the AI is working. These are NOT chat bubbles — they are small inline status lines:

```
⟳ Using HookDiagnosis...
✓ HookDiagnosis complete
⟳ Using EngagementCorrelation...
✓ EngagementCorrelation complete
```

Each line appears in real time driven by the SSE events from the backend:
- `skill_start` event → show "⟳ Using SkillName..."
- `skill_complete` event → spinning indicator becomes a green `✓`
- `token` events → AI response starts streaming in character by character with a blinking cursor
- `done` event → stream ends, cursor disappears

These skill log lines stay visible in the thread permanently so the user can always see which skills were used for any given answer.

### Bottom input (fixed)
A wide text input field. Placeholder: "Ask about your videos...". Sky blue send button (arrow icon) on the right. Press enter or click send to submit.

---

## Video References in Chat

When the AI responds and mentions a specific video, it uses the video's title — the same title visible in the sidebar card. This way the user can look left at the sidebar and immediately find which video is being discussed. Creator videos vs competitor videos are visually distinct by their role badge color.

---

## Technical Clarifications

### Inline Playback vs Modal vs PIP
- **Modal:** An overlay covers the entire page and the video plays in a popup in the center. Everything behind it is dimmed.
- **PIP (Picture-in-Picture):** A small floating video window that you can drag around the screen, sitting on top of all other content (like YouTube's mini-player when you scroll down).
- **Inline playback (what we use):** The thumbnail image simply becomes a video player in the exact same card position. No overlay, no popup, nothing moves. Think of how Twitter/X plays videos right in the feed.

### Single Page App (no URL changes)
The URL in the browser never changes. React manages what's shown through state — "are we on the projects list?" or "are we inside project X?". No React Router, no page navigation, no reloads. Everything is one app.

### SSE (Server-Sent Events)
The chat endpoint (`POST /projects/{id}/chat`) returns a streaming response. Instead of waiting for the full AI response and getting it all at once, the backend sends small chunks as they are produced. The frontend listens to this stream and renders each chunk as it arrives — that's what makes the text appear character by character and the skill log update in real time.

---

## Full New User Flow

1. Open app → see Projects page (empty state: "Create your first project")
2. Click `+ New Project` → type a name → instantly in the empty workspace
3. Left sidebar shows URL input box
4. Paste a YouTube or TikTok URL → press enter
5. Placeholder card appears with "Downloading..." status
6. Status progresses: Downloading → Transcribing → Indexing
7. Thumbnail pops in — hover to see play button, click chart icon for engagement metrics
8. Add more videos, each processes independently
9. Click `+ New Chat` at the bottom of the sidebar
10. Type a question in the chat area → send
11. Watch the skill log appear live: "⟳ Using HookDiagnosis... ✓ complete"
12. AI response streams in token by token
13. Continue chatting, or click `+ New Chat` for a fresh session
14. Previous sessions remain accessible in the bottom of the sidebar

---

## API Endpoints Used

| Action | Method | Endpoint |
|---|---|---|
| Create project | POST | `/projects` |
| Ingest video URLs | POST | `/projects/{id}/ingest` |
| Trigger transcription | POST | `/projects/{id}/videos/{vid}/transcribe` |
| Trigger indexing | POST | `/projects/{id}/videos/{vid}/index` |
| List videos with metrics | GET | `/projects/{id}/videos` |
| Streaming chat | POST | `/projects/{id}/chat` (SSE) |
| Chat session history | GET | `/projects/{id}/chat/sessions/{sid}/history` |
| List projects | GET | `/projects` |
| Get project details | GET | `/projects/{id}` |
