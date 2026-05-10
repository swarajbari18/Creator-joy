import asyncio
import json
from pathlib import Path
from qdrant_client import QdrantClient
from creator_joy.rag.models import RAGSettings
from creator_joy.rag.service import RAGService

async def check_qdrant():
    settings = RAGSettings()
    client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    collection = settings.collection_name
    
    project_id = "3df4639d-95b3-47a9-9c99-1859ae5a40d8"
    video_ids = [
        "ec375fe7-3635-4bcc-9f8f-3cf89abb1d15",
        "7bcda575-5741-4260-8e19-ee6558c164e2"
    ]
    
    print(f"Checking collection: {collection}")
    
    for v_id in video_ids:
        res = client.count(
            collection_name=collection,
            count_filter={
                "must": [
                    {"key": "video_id", "match": {"value": v_id}}
                ]
            }
        )
        print(f"Video {v_id}: {res.count} segments found.")

    # Check total points in collection
    total = client.count(collection_name=collection)
    print(f"Total segments in collection: {total.count}")

if __name__ == "__main__":
    asyncio.run(check_qdrant())
