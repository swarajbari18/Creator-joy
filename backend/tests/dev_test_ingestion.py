from __future__ import annotations

from pathlib import Path

from creator_joy.ingestion import IngestionSettings, VideoIngestionService
from creator_joy.ingestion.logging_config import configure_debug_logging


STORAGE_ROOT = Path("downloads")
PROJECT_NAME = "Local Ingestion Test"
PROJECT_DESCRIPTION = "Manual developer test for the local video ingestion component."

# Put the two real challenge/demo URLs here while testing.
VIDEO_URLS = [
    "https://www.youtube.com/watch?v=d0wUM8hIaxE",
    "https://www.youtube.com/watch?v=1lqjfa-FlPc"
]


def run_ingestion_test() -> None:
    configure_debug_logging()

    settings = IngestionSettings(storage_root=STORAGE_ROOT)
    service = VideoIngestionService(settings)

    project = service.create_project(
        name=PROJECT_NAME,
        description=PROJECT_DESCRIPTION,
    )
    print(f"\nCreated project: {project.id} | {project.name}")

    print(f"\nIngesting {len(VIDEO_URLS)} URL(s)")
    videos = service.ingest_urls(project_id=project.id, urls=VIDEO_URLS)

    print("\nVideo rows")
    for video in videos:
        print(
            f"- video_id={video.id} status={video.status.value} "
            f"title={video.title!r} error={video.error_message!r}"
        )

        files = service.list_video_files(video.id)
        for file in files:
            print(
                f"  - {file.kind.value}: {file.path} "
                f"ext={file.ext!r} size_bytes={file.size_bytes}"
            )

    print(f"\nSQLite database: {settings.database_path}")
    print(f"Storage root: {settings.storage_root.resolve()}")


if __name__ == "__main__":
    run_ingestion_test()
