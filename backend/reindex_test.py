import asyncio
import logging
import sys
from pathlib import Path
from creator_joy.rag.service import RAGService
from creator_joy.rag.models import RAGSettings

logging.basicConfig(level=logging.DEBUG)

async def reindex_test():
    video_id = "ec375fe7-3635-4bcc-9f8f-3cf89abb1d15"
    print(f"Starting re-index test for video: {video_id}")
    
    try:
        service = RAGService(RAGSettings())
        record = service.index_video(video_id)
        print(f"Indexing finished. Status: {record.status}, Segments: {record.segments_indexed}")
    except Exception as e:
        print(f"FATAL ERROR during indexing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(reindex_test())
