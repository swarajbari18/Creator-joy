from pydantic import BaseModel
from typing import Optional, List

class CreateProjectRequest(BaseModel):
    name: str

class IngestRequest(BaseModel):
    urls: list[str]
    roles: list[str]  # "creator" or "competitor" — one per URL

class ChatRequest(BaseModel):
    session_id: str
    message: str

class VideoResponse(BaseModel):
    id: str
    url: str
    title: str
    role: str
    status: str
    er_views: Optional[float] = None
    view_count: Optional[int] = None
    duration_seconds: Optional[int] = None
