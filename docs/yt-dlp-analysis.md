# yt-dlp Integration Analysis for Agentic Application

## TL;DR — The Best Approach

> [!IMPORTANT]
> **Do NOT clone the yt-dlp repo into your project.** Install it as a pip dependency (`pip install yt-dlp`) and use its **Python embedding API** directly. yt-dlp is designed for this — it has a full-featured `YoutubeDL` class that you import and use programmatically.

---

## Three Integration Approaches Compared

| Approach | Verdict | Why |
|---|---|---|
| **`pip install yt-dlp`** (Python library) | ✅ **Recommended** | First-class Python API, rich `info_dict` returns, proper error handling, progress hooks, custom post-processors |
| **`subprocess.run("yt-dlp ...")` (CLI wrapper)** | ⚠️ Acceptable fallback | Works, but you lose type safety, structured data, and have to parse stdout/JSON output |
| **Clone/submodule the repo** | ❌ **Don't do this** | Massive codebase (~2000+ files), painful to update, no isolation, merge conflicts, licensing headaches |

---

## Why the Python API is Perfect for Agentic Use

yt-dlp explicitly supports embedding. From their README:

```python
from yt_dlp import YoutubeDL

URLS = ['https://www.youtube.com/watch?v=BaW_jenozKc']
with YoutubeDL() as ydl:
    ydl.download(URLS)
```

But more importantly for an **agent**, you get:

### 1. Metadata Extraction Without Downloading
```python
import yt_dlp

def extract_video_info(url: str) -> dict:
    """Agent can inspect video metadata before deciding to download."""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return ydl.sanitize_info(info)  # Makes it JSON-serializable
```

This returns a rich dictionary with:
- `title`, `description`, `duration`, `view_count`
- `uploader`, `channel`, `upload_date`
- `formats` (all available quality options)
- `thumbnails`, `subtitles`, `chapters`
- Platform-specific metadata

### 2. Progress Hooks (Real-time Agent Feedback)
```python
def progress_callback(d):
    if d['status'] == 'downloading':
        percent = d.get('_percent_str', 'N/A')
        speed = d.get('_speed_str', 'N/A')
        # Feed this into your agent's state/UI
    elif d['status'] == 'finished':
        filepath = d['filename']
        # Notify agent that download is complete

ydl_opts = {
    'progress_hooks': [progress_callback],
}
```

### 3. Custom Post-Processors
```python
class AgentPostProcessor(yt_dlp.postprocessor.PostProcessor):
    def run(self, info):
        # Trigger agent actions after download:
        # - Move file to storage
        # - Update database
        # - Notify user
        # - Trigger transcription pipeline
        return [], info
```

### 4. Structured Error Handling
```python
from yt_dlp.utils import DownloadError, ExtractorError

try:
    info = ydl.extract_info(url, download=False)
except DownloadError as e:
    # Network/download failure — agent can retry
except ExtractorError as e:
    # Site-specific extraction failure — agent can try fallback
```

---

## Supported Sites (Not Just YouTube!)

yt-dlp supports **thousands** of sites including:

| Category | Examples |
|---|---|
| **Video Platforms** | YouTube, Vimeo, Dailymotion, Twitch, TikTok, Bilibili |
| **Social Media** | Twitter/X, Instagram, Facebook, Reddit, Threads |
| **Music** | SoundCloud, Bandcamp, Spotify (metadata), Mixcloud |
| **Streaming** | Crunchyroll, Funimation, Disney+, Netflix (with auth) |
| **News/Media** | BBC, CNN, NBC, ABC, CBS |
| **Education** | Udemy, Coursera, Khan Academy |
| **Misc** | Imgur, Tumblr, Pinterest, Archive.org |

The "generic" extractor also handles any page with embedded `<video>` or `<audio>` tags, m3u8/DASH manifests, etc.

---

## Recommended Architecture for Your Agentic App

```
Creator-joy/
├── pyproject.toml              # yt-dlp as dependency
├── src/
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── core.py             # Agent orchestration logic
│   │   └── tools/
│   │       ├── __init__.py
│   │       ├── downloader.py   # yt-dlp wrapper (the "tool")
│   │       ├── metadata.py     # Video info extraction tool
│   │       └── formats.py      # Format selection logic
│   ├── config/
│   │   └── download_presets.py # Quality presets, output templates
│   └── models/
│       └── video.py            # Video dataclass/pydantic model
├── downloads/                  # Default download directory
└── tests/
```

### Core Downloader Tool

```python
# src/agent/tools/downloader.py
import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError
from dataclasses import dataclass
from typing import Optional, Callable
import logging

logger = logging.getLogger(__name__)

@dataclass
class DownloadResult:
    success: bool
    filepath: Optional[str] = None
    title: Optional[str] = None
    duration: Optional[float] = None
    error: Optional[str] = None
    metadata: Optional[dict] = None

class VideoDownloader:
    """Agentic yt-dlp wrapper — works with ANY supported social link."""
    
    DEFAULT_OPTS = {
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4',
        'outtmpl': '%(title)s [%(id)s].%(ext)s',
        'restrictfilenames': True,
    }
    
    def __init__(self, download_dir: str = './downloads', 
                 on_progress: Optional[Callable] = None):
        self.download_dir = download_dir
        self.on_progress = on_progress
    
    def get_info(self, url: str) -> DownloadResult:
        """Extract metadata without downloading — agent decision point."""
        opts = {
            **self.DEFAULT_OPTS,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                safe_info = ydl.sanitize_info(info)
                return DownloadResult(
                    success=True,
                    title=safe_info.get('title'),
                    duration=safe_info.get('duration'),
                    metadata=safe_info,
                )
        except (DownloadError, ExtractorError) as e:
            return DownloadResult(success=False, error=str(e))
    
    def download(self, url: str, 
                 format: str = 'bestvideo+bestaudio/best',
                 audio_only: bool = False) -> DownloadResult:
        """Download video/audio from any supported social link."""
        opts = {
            **self.DEFAULT_OPTS,
            'format': format,
            'paths': {'home': self.download_dir},
        }
        
        if audio_only:
            opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        
        if self.on_progress:
            opts['progress_hooks'] = [self.on_progress]
        
        result_filepath = None
        
        def capture_filepath(d):
            nonlocal result_filepath
            if d['status'] == 'finished':
                result_filepath = d.get('filename')
        
        opts.setdefault('progress_hooks', []).append(capture_filepath)
        
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url)
                safe_info = ydl.sanitize_info(info)
                return DownloadResult(
                    success=True,
                    filepath=result_filepath,
                    title=safe_info.get('title'),
                    duration=safe_info.get('duration'),
                    metadata=safe_info,
                )
        except (DownloadError, ExtractorError) as e:
            logger.error(f"Download failed for {url}: {e}")
            return DownloadResult(success=False, error=str(e))
    
    def list_formats(self, url: str) -> list[dict]:
        """List all available formats — agent can pick the right one."""
        info = self.get_info(url)
        if not info.success or not info.metadata:
            return []
        return info.metadata.get('formats', [])
```

---

## Installation & Dependencies

```bash
# In your project
pip install "yt-dlp[default]"

# For browser impersonation (recommended for TikTok, Instagram, etc.)
pip install "yt-dlp[default,curl-cffi]"

# ffmpeg is REQUIRED for merging video+audio streams
# Ubuntu/Debian:
sudo apt install ffmpeg

# Or use yt-dlp's own builds:
# https://github.com/yt-dlp/FFmpeg-Builds
```

### pyproject.toml
```toml
[project]
dependencies = [
    "yt-dlp[default]>=2024.0.0",
]

[project.optional-dependencies]
impersonate = [
    "yt-dlp[default,curl-cffi]",
]
```

---

## Key API Methods You'll Use

| Method | Purpose |
|---|---|
| `ydl.extract_info(url, download=False)` | Get metadata only (agent inspects before deciding) |
| `ydl.extract_info(url)` | Extract info AND download |
| `ydl.download([url1, url2])` | Download multiple URLs |
| `ydl.sanitize_info(info)` | Make info_dict JSON-serializable |
| `ydl.download_with_info_file(path)` | Download from a saved .info.json |
| `ydl.add_post_processor(pp, when=...)` | Add custom post-processing |

---

## Open Questions

1. **What language/framework** are you building the agent in? (Python with LangChain/CrewAI? Or a Node.js/TypeScript frontend with a Python backend?)
2. **What's the agent's primary use case?** (e.g., "user pastes a social media link and the agent downloads + processes it" — or more complex workflows?)
3. **Do you need authentication** for any platforms? (e.g., private Instagram posts, Patreon, etc.)
4. **Where should downloads be stored?** (Local disk, cloud storage like S3/GCS, etc.)
5. **Do you want the agent to also handle** audio extraction, subtitle downloads, thumbnail extraction, or just video?
