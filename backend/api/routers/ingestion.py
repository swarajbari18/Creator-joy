from fastapi import APIRouter, HTTPException
from pathlib import Path
from ..models import IngestRequest
from creator_joy.ingestion.service import VideoIngestionService
from creator_joy.ingestion.models import IngestionSettings

router = APIRouter()

@router.post("/{project_id}/videos/{video_id}/transcribe")
async def transcribe_video(project_id: str, video_id: str):
    from creator_joy.transcription.service import TranscriptionService
    service = TranscriptionService()
    record = service.transcribe_video(video_id)
    return {"id": record.id, "video_id": record.video_id, "status": record.status, "error_message": record.error_message}

@router.post("/{project_id}/videos/{video_id}/index")
async def index_video(project_id: str, video_id: str):
    from creator_joy.rag.service import RAGService
    from creator_joy.rag.models import RAGSettings
    service = RAGService(RAGSettings())
    record = service.index_video(video_id)
    return {"id": record.id, "video_id": record.video_id, "status": record.status, "segments_indexed": record.segments_indexed, "error_message": record.error_message}

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
