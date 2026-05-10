import json
import asyncio
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from ..models import ChatRequest
from creator_joy.ingestion.models import IngestionSettings

router = APIRouter()

DB_PATH = IngestionSettings().database_path

@router.post("/{project_id}/chat")
async def chat_stream(project_id: str, request: ChatRequest):
    from creator_joy.chat.service import ChatService
    service = ChatService(db_path=DB_PATH)
    
    async def event_generator():
        async for event in service.stream_response(
            project_id=project_id,
            session_id=request.session_id,
            user_message=request.message,
        ):
            yield f"data: {json.dumps(event)}\n\n"
            await asyncio.sleep(0)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",      # disable nginx buffering
            "Connection": "keep-alive",
        },
    )

@router.get("/{project_id}/chat/sessions")
async def list_sessions(project_id: str):
    from creator_joy.chat.memory import ChatMemory
    memory = ChatMemory(db_path=DB_PATH)
    return memory.list_sessions(project_id)

@router.get("/{project_id}/chat/sessions/{session_id}/history")
async def get_chat_history(project_id: str, session_id: str):
    from creator_joy.chat.memory import ChatMemory
    memory = ChatMemory(db_path=DB_PATH)
    history = memory.load_history(session_id)
    return {"history": history}
