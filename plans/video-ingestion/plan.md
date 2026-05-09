# Video Ingestion Component Plan

## Goal

Build the first backend component for Creator Joy: a deterministic Python ingestion library that takes a project and one or more public social video URLs, downloads the videos, extracts audio, captures all `yt-dlp` metadata, and stores project/video/file relationships in SQLite.

This component is intentionally not an LLM step. Gemini, LangChain, vector DB ingestion, rich transcription, engagement-rate computation, and chat come later.

## Scope

Included in this implementation:

- Create and retrieve local projects.
- Ingest one or more URLs into a project.
- Download a merged playable video file for each URL.
- Download/extract a separate audio file for each URL.
- Save the full sanitized `yt-dlp` metadata JSON without filtering fields down.
- Store project, video, and file records in SQLite.
- Preserve failed download attempts with loud error details.
- Provide debug logs that explain the ingestion flow step by step.
- Provide a direct Python developer test script for local end-to-end testing.

Excluded from this implementation:

- LLM analysis.
- Gemini rich transcription.
- Vector DB storage.
- Engagement-rate computation.
- Authenticated/private platform support.
- Browser cookies.
- Production API endpoints.
- Frontend UI.

## Storage Layout

The local storage root defaults to `downloads/` under the backend directory.

```text
backend/downloads/
  creator_joy.sqlite3
  projects/
    {project_id}/
      videos/
        {video_id}/
          source_video.ext
          audio.ext
          metadata.json
```

Internal UUIDs are used for project and video directory names. Platform IDs and titles are stored as metadata, not used as primary storage keys.

## SQLite Data Model

### `projects`

- `id`
- `name`
- `description`
- `created_at`
- `updated_at`

### `videos`

- `id`
- `project_id`
- `source_url`
- `normalized_url`
- `platform`
- `yt_dlp_id`
- `title`
- `uploader`
- `duration`
- `upload_date`
- `status`
- `error_message`
- `metadata_path`
- `created_at`
- `updated_at`

### `video_files`

- `id`
- `video_id`
- `kind`
- `path`
- `ext`
- `size_bytes`
- `created_at`

Supported file kinds:

- `video`
- `audio`
- `metadata`
- `thumbnail`
- `other`

## Download Behavior

Use `yt-dlp` through its Python API.

For each URL:

1. Validate that the target project exists.
2. Create or reset a video row for that project and URL.
3. Create the local video storage directory.
4. Mark the video `downloading`.
5. Download the merged video file.
6. Download/extract a separate audio file.
7. Save the full sanitized metadata to `metadata.json`.
8. Register generated files in SQLite.
9. Copy useful metadata fields into the `videos` row for querying.
10. Mark the video `completed`.

On failure:

- keep the video row,
- mark it `failed`,
- store the error message,
- log the exception with stack trace,
- continue processing the rest of the batch.

## Dependency Policy

The code should fail loud and clear.

- `yt-dlp` is imported normally by the downloader module.
- If `yt-dlp` is missing, importing or running the ingestion component fails immediately.
- `ffmpeg` is checked before downloading.
- If `ffmpeg` is missing, ingestion raises a clear dependency error before partial media work begins.

## Duplicate URL Policy

- The same URL is allowed in different projects.
- The same URL inside the same project maps to one video row.
- If the previous row failed or completed, re-ingesting the same URL resets that row and retries it.

## Observability

Debug logs are mandatory.

The component logs:

- database initialization,
- project creation,
- URL registration,
- duplicate URL reset,
- directory creation,
- dependency checks,
- yt-dlp start/end events,
- yt-dlp progress hook events,
- metadata save path,
- file registration,
- status transitions,
- failures with stack traces.

The local developer test script enables debug logging by default so a developer can see the full flow.

## Acceptance Criteria

- A developer can create a project and ingest URLs from Python.
- A developer can run `backend/dev_test_ingestion.py` directly for end-to-end testing.
- Completed ingestions produce local video, audio, and metadata files.
- SQLite links each project to its videos and each video to its files.
- Full raw `yt-dlp` metadata is preserved.
- Missing dependencies fail loudly.
- Failed downloads are visible in both logs and SQLite.
