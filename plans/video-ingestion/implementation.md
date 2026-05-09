# Video Ingestion Implementation Notes

This document explains the implementation details for the local Python video ingestion component. It should be updated whenever the ingestion code changes.

## Files Created

### `backend/creator_joy/__init__.py`

Package marker for the backend source package.

### `backend/requirements.txt`

Installs external Python dependencies into `backend/venv`.

Current dependency:

- `yt-dlp[default,curl-cffi]>=2025.0.0`

### `backend/creator_joy/ingestion/__init__.py`

Exports the public ingestion API:

- `VideoIngestionService`
- `IngestionSettings`
- data models such as `ProjectRecord`, `VideoRecord`, and `VideoFileRecord`

### `backend/creator_joy/ingestion/models.py`

Contains lightweight dataclasses and enums shared across the component.

Important types:

- `VideoStatus`: lifecycle status for a video row.
- `VideoFileKind`: type of artifact stored for a video.
- `ProjectRecord`: project row returned from SQLite.
- `VideoRecord`: video row returned from SQLite.
- `VideoFileRecord`: file row returned from SQLite.
- `DownloadedArtifacts`: in-memory result from the downloader before it is committed back into SQLite.
- `IngestionSettings`: paths and download settings used by the service.

### `backend/creator_joy/ingestion/logging_config.py`

Contains `configure_debug_logging()`.

The developer test script calls this by default. Library callers may also call it while debugging.

### `backend/creator_joy/ingestion/database.py`

Owns SQLite persistence.

Responsibilities:

- Create tables if they do not exist.
- Insert and fetch projects.
- Create or reset video rows for a project URL.
- Update video status and metadata fields.
- Insert file records.
- Return project videos and video file lists.

Output of this layer:

- Stable project/video/file IDs.
- Rows that the service uses to decide where files should live.
- Queryable state after ingestion.

### `backend/creator_joy/ingestion/downloader.py`

Owns all direct `yt-dlp` interaction.

Responsibilities:

- Import `yt_dlp` normally so missing dependencies fail loudly.
- Check that `ffmpeg` exists before ingestion.
- Download a merged playable video.
- Download/extract separate audio.
- Sanitize and return the full metadata dictionary.
- Download thumbnails for later UI preview.
- Keep subtitle downloads disabled because rich transcription will come from video/audio.
- Save no database state directly.
- Let `yt-dlp` own the output directory through `paths.home`, while `outtmpl` uses filename-only templates like `source_video.%(ext)s` and `audio.%(ext)s`. This prevents duplicated nested paths under `downloads/projects/...`.

Output of this layer:

- `DownloadedArtifacts`, containing the metadata dictionary plus local video, audio, and thumbnail paths.

### `backend/creator_joy/ingestion/service.py`

Coordinates database and downloader work.

Responsibilities:

- Expose the public library API.
- Validate project existence.
- Register URL ingestion attempts.
- Create per-video storage directories.
- Call the downloader.
- Save `metadata.json`.
- Validate required video/audio files after metadata is saved.
- Register video/audio/thumbnail/metadata files.
- Mark videos completed or failed.
- Keep batch ingestion moving when one URL fails.

Input/output relationship:

1. A caller passes `project_id` and URLs to `ingest_urls()`.
2. `service.py` asks `database.py` to create/reset video rows.
3. The returned `VideoRecord.id` determines the filesystem directory.
4. `service.py` passes that directory and URL to `downloader.py`.
5. `downloader.py` returns local files and metadata.
6. `service.py` writes metadata JSON immediately.
7. `service.py` validates video/audio paths, then records video, audio, thumbnail, and metadata files through `database.py`.
8. The final `VideoRecord` returned to the caller reflects success or failure.

### `backend/tests/dev_test_ingestion.py`

Direct Python developer test for the ingestion component.

This is intentionally not a CLI wrapper around the library. It imports and calls the same Python service API that later backend/API code will use:

- `VideoIngestionService(...)`
- `service.create_project(...)`
- `service.ingest_urls(...)`
- `service.list_video_files(...)`

The file has a normal `if __name__ == "__main__"` block so it can be run as a Python module from the `backend/` folder while still making the function calls explicit.

## How To Run Locally

Create a virtual environment inside `backend/`:

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
```

Install backend dependencies from inside `backend/`:

```bash
python -m pip install -r requirements.txt
```

After that, this import should work from inside the same activated virtual environment because `creator_joy/` is directly inside `backend/`:

```bash
python -c "from creator_joy.ingestion import VideoIngestionService; print(VideoIngestionService)"
```

Install `ffmpeg` if it is not already installed:

```bash
sudo apt install ffmpeg
```

Run the direct Python test:

```bash
python -m tests.dev_test_ingestion
```

To test with specific videos, edit `VIDEO_URLS` in `backend/tests/dev_test_ingestion.py` and run the same command again.

The test writes local data to:

```text
backend/downloads/
```

The expected output includes:

- debug logs for the full flow,
- the created project ID,
- one row per ingested video,
- one row per stored file,
- the SQLite database path,
- the storage root path.

## Developer Testing Expectations

End-to-end developer test:

1. Create a project.
2. Put one or two short public video URLs in `VIDEO_URLS`.
3. Run `python -m tests.dev_test_ingestion`.
4. Confirm logs show dependency checks, status transitions, download progress, file registration, and completion.
5. Confirm `backend/downloads/creator_joy.sqlite3` exists.
6. Confirm `backend/downloads/projects/{project_id}/videos/{video_id}/` contains video, audio, and `metadata.json`.

Failure test:

1. Ingest an invalid URL.
2. Confirm the script logs the failure clearly.
3. Confirm the video row remains in SQLite with status `failed`.
4. Confirm the batch continues if multiple URLs were provided.

Dependency test:

1. Run without `yt-dlp` installed.
2. Confirm import/runtime fails loudly instead of pretending ingestion is available.
3. Run without `ffmpeg`.
4. Confirm ingestion stops before download with a clear dependency error.

## Observability Notes

The component uses Python `logging`.

Logger namespace:

```text
creator_joy.ingestion
```

Debug logs are intentionally verbose in `backend/tests/dev_test_ingestion.py`. They are meant to help a developer follow the exact flow without opening the database manually.
