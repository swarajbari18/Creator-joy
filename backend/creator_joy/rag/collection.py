import logging
from qdrant_client import QdrantClient, models

logger = logging.getLogger(__name__)

def ensure_collection(client: QdrantClient, collection_name: str, embedding_dim: int) -> None:
    """Create collection + all payload indexes if they don't exist yet."""
    existing = [c.name for c in client.get_collections().collections]
    if collection_name in existing:
        logger.debug("Collection %s already exists", collection_name)
        return
    
    logger.debug("Creating collection %s dim=%s", collection_name, embedding_dim)
    
    client.create_collection(
        collection_name=collection_name,
        vectors_config={
            "dense_transcript": models.VectorParams(
                size=embedding_dim,
                distance=models.Distance.COSINE,
                hnsw_config=models.HnswConfigDiff(m=16, ef_construct=100),
            ),
            "dense_production": models.VectorParams(
                size=embedding_dim,
                distance=models.Distance.COSINE,
                hnsw_config=models.HnswConfigDiff(m=16, ef_construct=100),
            ),
        },
        sparse_vectors_config={
            "sparse_minicoil": models.SparseVectorParams(
                modifier=models.Modifier.IDF
            )
        },
    )

    # project_id — tenant index for HNSW co-location
    client.create_payload_index(
        collection_name=collection_name,
        field_name="project_id",
        field_schema=models.KeywordIndexParams(
            type=models.KeywordIndexType.KEYWORD,
            is_tenant=True,
        ),
    )

    # video_id
    client.create_payload_index(
        collection_name=collection_name,
        field_name="video_id",
        field_schema=models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD),
    )

    # Structural filter fields
    keyword_fields = [
        "shot_type", "camera_angle", "camera_movement", "depth_of_field",
        "background_type", "key_light_direction", "light_quality",
        "color_temperature_feel", "music_genre_feel", "music_tempo_feel",
        "audio_quality", "color_grade_feel", "language", "speaker_id", "cut_type"
    ]
    for field in keyword_fields:
        client.create_payload_index(collection_name, field,
            models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD))

    bool_fields = [
        "speaker_visible", "music_present", "on_screen_text_present",
        "graphics_present", "cut_occurred", "catch_light_in_eyes"
    ]
    for field in bool_fields:
        client.create_payload_index(collection_name, field,
            models.BoolIndexParams(type=models.BoolIndexType.BOOL))

    float_fields = [
        "timecode_start_seconds", "timecode_end_seconds", "duration_seconds"
    ]
    for field in float_fields:
        client.create_payload_index(collection_name, field,
            models.FloatIndexParams(type=models.FloatIndexType.FLOAT))

    logger.debug("Collection %s created with all payload indexes", collection_name)
