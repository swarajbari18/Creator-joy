from fastapi import APIRouter, HTTPException
from pathlib import Path
from ..models import IngestRequest
from creator_joy.ingestion.service import VideoIngestionService
from creator_joy.ingestion.models import IngestionSettings

router = APIRouter()

@router.post("/{project_id}/ingest")
async def ingest_urls(project_id: str, request: IngestRequest):
    settings = IngestionSettings()
    service = VideoIngestionService(settings)
    
    # We need to handle roles. The service.ingest_urls doesn't support roles yet.
    # The plan says: "When a project is created via the API, the caller labels each URL as creator or competitor. This label is stored in SQLite videos table and injected here."
    
    results = []
    for url, role in zip(request.urls, request.roles):
        video = service.database.create_or_reset_video(project_id=project_id, source_url=url)
        service.database.update_video_role(video.id, role)
        try:
            final_video = service._ingest_one(video)
            results.append(final_video)
        except Exception as exc:
            service.database.update_video_status(
                video_id=video.id,
                status="failed",
                error_message=str(exc),
            )
            results.append(service.database.get_video(video.id))
            
    return results
