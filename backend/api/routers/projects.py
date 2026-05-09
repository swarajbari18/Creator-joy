from fastapi import APIRouter, HTTPException
from ..models import CreateProjectRequest
from creator_joy.ingestion.database import IngestionDatabase
from creator_joy.rag.models import RAGSettings

router = APIRouter()

@router.post("")
async def create_project(request: CreateProjectRequest):
    db = IngestionDatabase(RAGSettings().database_path)
    project = db.create_project(name=request.name)
    return project

@router.get("/{project_id}")
async def get_project(project_id: str):
    db = IngestionDatabase(RAGSettings().database_path)
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.get("/{project_id}/videos")
async def list_project_videos(project_id: str):
    db = IngestionDatabase(RAGSettings().database_path)
    videos = db.list_project_videos(project_id)
    return videos
