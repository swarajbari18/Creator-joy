from __future__ import annotations

import json
import logging
from pathlib import Path

from creator_joy.ingestion.database import IngestionDatabase
from creator_joy.ingestion.downloader import VideoDownloader
from creator_joy.ingestion.models import (
    IngestionSettings,
    ProjectRecord,
    VideoFileKind,
    VideoFileRecord,
    VideoRecord,
    VideoStatus,
)

logger = logging.getLogger(__name__)


class VideoIngestionService:
    def __init__(self, settings: IngestionSettings | None = None) -> None:
        self.settings = settings or IngestionSettings()
        logger.debug("Creating VideoIngestionService settings=%s", self.settings)
        self.settings.storage_root.mkdir(parents=True, exist_ok=True)
        self.database = IngestionDatabase(self.settings.database_path)
        self.downloader = VideoDownloader(self.settings)

    def create_project(self, name: str, description: str | None = None) -> ProjectRecord:
        logger.debug("Service create_project name=%s description=%s", name, description)
        return self.database.create_project(name=name, description=description)

    def get_project(self, project_id: str) -> ProjectRecord | None:
        logger.debug("Service get_project project_id=%s", project_id)
        return self.database.get_project(project_id)

    def list_projects(self) -> list[ProjectRecord]:
        logger.debug("Service list_projects")
        return self.database.list_projects()

    def ingest_urls(self, project_id: str, urls: list[str]) -> list[VideoRecord]:
        logger.debug("Service ingest_urls project_id=%s url_count=%s", project_id, len(urls))
        project = self.database.get_project(project_id)
        if project is None:
            raise ValueError(f"Project does not exist: {project_id}")

        results: list[VideoRecord] = []
        for url in urls:
            video = self.database.create_or_reset_video(project_id=project_id, source_url=url)
            try:
                final_video = self._ingest_one(video)
                results.append(final_video)
            except Exception as exc:
                logger.exception("Ingestion failed video_id=%s url=%s", video.id, url)
                self.database.update_video_status(
                    video_id=video.id,
                    status=VideoStatus.FAILED,
                    error_message=str(exc),
                )
                failed_video = self.database.get_video(video.id)
                if failed_video is None:
                    raise RuntimeError(f"Failed video row disappeared: {video.id}") from exc
                results.append(failed_video)
        return results

    def list_project_videos(self, project_id: str) -> list[VideoRecord]:
        logger.debug("Service list_project_videos project_id=%s", project_id)
        return self.database.list_project_videos(project_id)

    def get_video(self, video_id: str) -> VideoRecord | None:
        logger.debug("Service get_video video_id=%s", video_id)
        return self.database.get_video(video_id)

    def list_video_files(self, video_id: str) -> list[VideoFileRecord]:
        logger.debug("Service list_video_files video_id=%s", video_id)
        return self.database.list_video_files(video_id)

    def _ingest_one(self, video: VideoRecord) -> VideoRecord:
        logger.debug("Starting single-video ingestion video_id=%s url=%s", video.id, video.source_url)
        self.database.update_video_status(video.id, VideoStatus.DOWNLOADING)
        video_dir = self._video_directory(video.project_id, video.id)
        logger.debug("Ensuring video directory exists video_id=%s path=%s", video.id, video_dir)
        video_dir.mkdir(parents=True, exist_ok=True)

        artifacts = self.downloader.download(video.source_url, video_dir)
        metadata_path = video_dir / "metadata.json"
        logger.debug("Writing metadata JSON video_id=%s path=%s", video.id, metadata_path)
        metadata_path.write_text(
            json.dumps(artifacts.metadata, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        self._validate_required_artifacts(video.id, artifacts.video_paths, artifacts.audio_paths, video_dir)
        self.database.update_video_metadata(video.id, artifacts.metadata, metadata_path)
        for path in artifacts.video_paths:
            self.database.add_video_file(video.id, VideoFileKind.VIDEO, path)
        for path in artifacts.audio_paths:
            self.database.add_video_file(video.id, VideoFileKind.AUDIO, path)
        for path in artifacts.thumbnail_paths:
            self.database.add_video_file(video.id, VideoFileKind.THUMBNAIL, path)
        self.database.add_video_file(video.id, VideoFileKind.METADATA, metadata_path)

        self.database.update_video_status(video.id, VideoStatus.COMPLETED)
        completed = self.database.get_video(video.id)
        if completed is None:
            raise RuntimeError(f"Completed video row disappeared: {video.id}")
        logger.debug("Completed single-video ingestion video_id=%s", video.id)
        return completed

    def _video_directory(self, project_id: str, video_id: str) -> Path:
        return self.settings.storage_root / "projects" / project_id / "videos" / video_id

    @staticmethod
    def _validate_required_artifacts(
        video_id: str,
        video_paths: list[Path],
        audio_paths: list[Path],
        video_dir: Path,
    ) -> None:
        logger.debug(
            "Validating required artifacts video_id=%s video_paths=%s audio_paths=%s video_dir=%s",
            video_id,
            video_paths,
            audio_paths,
            video_dir,
        )
        if not video_paths:
            raise RuntimeError(f"yt-dlp completed but no source_video file was found in {video_dir}")
        if not audio_paths:
            raise RuntimeError(f"yt-dlp completed but no audio file was found in {video_dir}")
