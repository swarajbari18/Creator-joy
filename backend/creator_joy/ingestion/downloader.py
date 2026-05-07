from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError

from creator_joy.ingestion.models import DownloadedArtifacts, IngestionSettings

logger = logging.getLogger(__name__)


class DependencyError(RuntimeError):
    """Raised when a required system or Python dependency is missing."""


class VideoDownloader:
    def __init__(self, settings: IngestionSettings) -> None:
        self.settings = settings

    def verify_dependencies(self) -> None:
        logger.debug("Checking required dependency: ffmpeg")
        if shutil.which("ffmpeg") is None:
            raise DependencyError(
                "ffmpeg is required for video merging and audio extraction, but it was not found on PATH."
            )
        logger.debug("Dependency check passed: ffmpeg found")

    def download(self, url: str, output_dir: Path) -> DownloadedArtifacts:
        self.verify_dependencies()
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("Starting yt-dlp ingestion url=%s output_dir=%s", url, output_dir)

        video_metadata = self._download_video(url, output_dir)
        audio_metadata = self._download_audio(url, output_dir)
        metadata = video_metadata or audio_metadata
        if not metadata:
            raise RuntimeError(f"yt-dlp returned no metadata for URL: {url}")

        artifacts = DownloadedArtifacts(
            metadata=metadata,
            video_paths=self._find_files(output_dir, "source_video"),
            audio_paths=self._find_files(output_dir, "audio"),
            thumbnail_paths=self._find_thumbnail_files(output_dir),
        )
        logger.debug(
            "yt-dlp ingestion produced video_paths=%s audio_paths=%s thumbnail_paths=%s",
            artifacts.video_paths,
            artifacts.audio_paths,
            artifacts.thumbnail_paths,
        )
        return artifacts

    def _download_video(self, url: str, output_dir: Path) -> dict[str, Any]:
        logger.debug("Starting merged video download url=%s", url)
        options = self._base_options(output_dir) | {
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": self.settings.video_merge_format,
            "outtmpl": "source_video.%(ext)s",
            "progress_hooks": [self._progress_hook("video")],
        }
        return self._extract(url, options)

    def _download_audio(self, url: str, output_dir: Path) -> dict[str, Any]:
        logger.debug("Starting separate audio extraction url=%s", url)
        options = self._base_options(output_dir) | {
            "format": "bestaudio/best",
            "outtmpl": "audio.%(ext)s",
            "progress_hooks": [self._progress_hook("audio")],
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": self.settings.audio_codec,
                    "preferredquality": self.settings.audio_quality,
                }
            ],
        }
        return self._extract(url, options)

    def _extract(self, url: str, options: dict[str, Any]) -> dict[str, Any]:
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                sanitized = ydl.sanitize_info(info)
                logger.debug(
                    "yt-dlp extraction complete extractor=%s id=%s title=%s",
                    sanitized.get("extractor_key") or sanitized.get("extractor"),
                    sanitized.get("id"),
                    sanitized.get("title"),
                )
                return sanitized
        except (DownloadError, ExtractorError):
            logger.exception("yt-dlp failed for url=%s", url)
            raise

    def _base_options(self, output_dir: Path) -> dict[str, Any]:
        return {
            "quiet": self.settings.ytdlp_quiet,
            "no_warnings": self.settings.ytdlp_no_warnings,
            "paths": {"home": str(output_dir)},
            "restrictfilenames": True,
            "noplaylist": True,
            "writethumbnail": True,
            "writesubtitles": False,
            "writeautomaticsub": False,
        }

    def _progress_hook(self, label: str):
        def hook(event: dict[str, Any]) -> None:
            status = event.get("status")
            filename = event.get("filename")
            percent = event.get("_percent_str")
            speed = event.get("_speed_str")
            eta = event.get("_eta_str")
            logger.debug(
                "yt-dlp progress label=%s status=%s filename=%s percent=%s speed=%s eta=%s",
                label,
                status,
                filename,
                percent,
                speed,
                eta,
            )

        return hook

    @staticmethod
    def _find_files(output_dir: Path, stem: str) -> list[Path]:
        return sorted(
            path for path in output_dir.iterdir()
            if path.is_file() and path.stem == stem and not path.name.endswith(".part")
        )

    @staticmethod
    def _find_thumbnail_files(output_dir: Path) -> list[Path]:
        return sorted(
            path for path in output_dir.iterdir()
            if path.is_file()
            and path.stem.startswith("source_video")
            and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        )
