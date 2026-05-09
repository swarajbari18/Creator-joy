import asyncio
from fastapi import APIRouter, HTTPException
from ..models import IngestRequest
from creator_joy.ingestion.service import VideoIngestionService
from creator_joy.ingestion.models import IngestionSettings

router = APIRouter()

@router.get("/{project_id}/videos/{video_id}/pipeline-status")
async def get_pipeline_status(project_id: str, video_id: str):
    from creator_joy.ingestion.models import IngestionSettings
    from creator_joy.ingestion.database import IngestionDatabase
    from creator_joy.transcription.database import TranscriptionDatabase
    from creator_joy.rag.database import RAGDatabase
    from creator_joy.rag.models import RAGSettings
    db_path = IngestionSettings().database_path
    trans_db = TranscriptionDatabase(db_path)
    rag_db = RAGDatabase(db_path)
    trans = trans_db.get_transcription_for_video(video_id)
    rag = rag_db.get_index_record_for_video(video_id)
    return {
        "transcription_status": trans.status if trans else None,
        "rag_status": rag.status if rag else None,
    }

@router.post("/{project_id}/videos/{video_id}/transcribe")
async def transcribe_video(project_id: str, video_id: str):
    from creator_joy.transcription.service import TranscriptionService
    service = TranscriptionService()
    record = await asyncio.to_thread(service.transcribe_video, video_id)
    return {"id": record.id, "video_id": record.video_id, "status": record.status, "error_message": record.error_message}

@router.post("/{project_id}/videos/{video_id}/index")
async def index_video(project_id: str, video_id: str):
    from creator_joy.rag.service import RAGService
    from creator_joy.rag.models import RAGSettings
    service = RAGService(RAGSettings())
    record = await asyncio.to_thread(service.index_video, video_id)
    return {"id": record.id, "video_id": record.video_id, "status": record.status, "segments_indexed": record.segments_indexed, "error_message": record.error_message}

@router.post("/{project_id}/ingest")
async def ingest_urls(project_id: str, request: IngestRequest):
    settings = IngestionSettings()
    service = VideoIngestionService(settings)

    results = []
    for url, role in zip(request.urls, request.roles):
        video = service.database.create_or_reset_video(project_id=project_id, source_url=url)
        service.database.update_video_role(video.id, role)
        try:
            final_video = await asyncio.to_thread(service._ingest_one, video)
            results.append(final_video)
        except Exception as exc:
            service.database.update_video_status(
                video_id=video.id,
                status="failed",
                error_message=str(exc),
            )
            results.append(service.database.get_video(video.id))

    return results
