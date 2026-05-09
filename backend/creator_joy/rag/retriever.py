import logging
from typing import Literal
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, Range, MatchAny
from qdrant_client import models

from creator_joy.rag.models import SearchResult, SegmentResult, StructuralFilters, RAGSettings
from creator_joy.rag.embedder import DenseEmbedder, SparseEmbedder
from creator_joy.rag.reranker import CrossEncoderReranker

logger = logging.getLogger(__name__)

def _payload_to_segment_result(payload: dict, score: float, point_id: str = "") -> SegmentResult:
    return SegmentResult(
        point_id=point_id or str(payload.get("point_id", "")),
        score=score,
        video_id=payload.get("video_id", ""),
        project_id=payload.get("project_id", ""),
        segment_id=payload.get("segment_id", 0),
        timecode_start=payload.get("timecode_start", ""),
        timecode_end=payload.get("timecode_end", ""),
        transcript=payload.get("transcript", ""),
        observable_summary=payload.get("observable_summary", ""),
        shot_type=payload.get("shot_type", ""),
        payload=payload,
    )

def _record_to_segment_result(record: models.Record | models.ScoredPoint, score: float) -> SegmentResult:
    return _payload_to_segment_result(record.payload or {}, score, str(record.id))

def _build_filter(
    project_id: str,
    video_ids: list[str] | None,
    filters: StructuralFilters | None,
) -> Filter:
    must = [
        FieldCondition(key="project_id", match=MatchValue(value=project_id))
    ]

    if video_ids:
        must.append(FieldCondition(key="video_id", match=MatchAny(any=video_ids)))

    if filters is None:
        return Filter(must=must)

    keyword_fields = [
        "shot_type", "camera_angle", "camera_movement", "depth_of_field",
        "background_type", "key_light_direction", "light_quality",
        "color_temperature_feel", "music_genre_feel", "music_tempo_feel",
        "audio_quality", "color_grade_feel", "language", "speaker_id", "cut_type",
    ]
    for field in keyword_fields:
        val = getattr(filters, field, None)
        if val is not None:
            must.append(FieldCondition(key=field, match=MatchValue(value=val)))

    bool_fields = [
        "speaker_visible", "music_present", "on_screen_text_present",
        "graphics_present", "cut_occurred", "catch_light_in_eyes",
    ]
    for field in bool_fields:
        val = getattr(filters, field, None)
        if val is not None:
            must.append(FieldCondition(key=field, match=MatchValue(value=val)))

    if filters.duration_min_seconds is not None or filters.duration_max_seconds is not None:
        must.append(FieldCondition(
            key="duration_seconds",
            range=Range(
                gte=filters.duration_min_seconds,
                lte=filters.duration_max_seconds,
            ),
        ))

    if filters.timecode_start_min_seconds is not None or filters.timecode_start_max_seconds is not None:
        must.append(FieldCondition(
            key="timecode_start_seconds",
            range=Range(
                gte=filters.timecode_start_min_seconds,
                lte=filters.timecode_start_max_seconds,
            ),
        ))

    return Filter(must=must)

def _structural_search(
    client: QdrantClient,
    collection_name: str,
    qdrant_filter: Filter,
    operation: str,
    group_by_field: str | None,
) -> SearchResult:

    if operation == "COUNT":
        count_result = client.count(
            collection_name=collection_name,
            count_filter=qdrant_filter,   # ← count_filter=
        )
        return SearchResult(
            mode="structural", operation="COUNT",
            total_count=count_result.count, segments=[], group_by_data=None,
        )

    # FETCH, SUM_duration, GROUP_BY — all need scroll
    all_records = []
    offset = None
    while True:
        records, next_offset = client.scroll(
            collection_name=collection_name,
            scroll_filter=qdrant_filter,   # ← scroll_filter= NOT filter=
            with_payload=True,
            limit=1000,
            offset=offset,
        )
        all_records.extend(records)
        if next_offset is None:
            break
        offset = next_offset

    if operation == "SUM_duration":
        total = sum(r.payload.get("duration_seconds", 0) for r in all_records if r.payload)
        return SearchResult(
            mode="structural", operation="SUM_duration",
            total_count=int(total), segments=[], group_by_data={"sum_duration_seconds": total},
        )

    if operation == "GROUP_BY":
        if group_by_field is None:
            raise ValueError("group_by_field required for GROUP_BY operation")
        groups: dict[str, int] = {}
        for r in all_records:
            if not r.payload: continue
            val = str(r.payload.get(group_by_field, "[missing]"))
            groups[val] = groups.get(val, 0) + 1
        return SearchResult(
            mode="structural", operation="GROUP_BY",
            total_count=len(all_records), segments=[],
            group_by_data={"field": group_by_field, "counts": groups},
        )

    # FETCH
    segments = [_record_to_segment_result(r, score=1.0) for r in all_records]
    return SearchResult(
        mode="structural", operation="FETCH",
        total_count=len(segments), segments=segments, group_by_data=None,
    )

def _semantic_search(
    client: QdrantClient,
    collection_name: str,
    nl_query: str,
    search_vector: str,
    project_id: str,
    qdrant_filter: Filter,
    top_k: int,
    prefetch_k: int,
    dense_embedder: DenseEmbedder,
    sparse_embedder: SparseEmbedder,
    reranker: CrossEncoderReranker,
    rerank_top_n: int,
) -> list[SegmentResult]:

    query_sparse = sparse_embedder.encode_query(nl_query)
    query_dense = dense_embedder.encode_query(nl_query)

    if search_vector == "both":
        # Two dense prefetches fused with RRF
        prefetch = [
            models.Prefetch(
                query=models.SparseVector(
                    indices=query_sparse.indices, values=query_sparse.values
                ),
                using="sparse_minicoil",
                filter=qdrant_filter,   # ← filter= inside Prefetch
                limit=prefetch_k,
            ),
            models.Prefetch(
                query=query_dense,
                using="dense_transcript",
                filter=qdrant_filter,
                limit=prefetch_k,
            ),
            models.Prefetch(
                query=query_dense,
                using="dense_production",
                filter=qdrant_filter,
                limit=prefetch_k,
            ),
        ]
    else:
        prefetch = [
            models.Prefetch(
                query=models.SparseVector(
                    indices=query_sparse.indices, values=query_sparse.values
                ),
                using="sparse_minicoil",
                filter=qdrant_filter,
                limit=prefetch_k,
            ),
            models.Prefetch(
                query=query_dense,
                using=search_vector,
                filter=qdrant_filter,
                limit=prefetch_k,
            ),
        ]

    results = client.query_points(
        collection_name=collection_name,
        prefetch=prefetch,
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        query_filter=qdrant_filter,     # ← query_filter= on query_points (NOT filter=)
        limit=top_k * 3,
        with_payload=True,
    )

    candidates = [dict(r.payload or {}, point_id=str(r.id)) for r in results.points]
    if nl_query and reranker and candidates:
        candidates = reranker.rerank(nl_query, candidates, top_n=rerank_top_n)

    segments = [_payload_to_segment_result(p, score=p.get("_rerank_score", 0.0), point_id=str(p.get("point_id", "")))
                for p in candidates[:top_k]]
    return segments

def search_segments(
    # ── Mode 1: Structural ──────────────────────────────────────────────────
    filters: StructuralFilters | None = None,
    operation: Literal["FETCH", "COUNT", "SUM_duration", "GROUP_BY"] = "FETCH",
    group_by_field: str | None = None,
    # ── Mode 2 & 3: Semantic ────────────────────────────────────────────────
    nl_query: str | None = None,
    search_vector: Literal["dense_transcript", "dense_production", "both"] = "dense_transcript",
    top_k: int = 10,
    
    *,
    client: QdrantClient,
    dense_embedder: DenseEmbedder,
    sparse_embedder: SparseEmbedder,
    reranker: CrossEncoderReranker,
    settings: RAGSettings,
    # ── Dependencies (injected by Langchain Tool Runtime. the agent never sees these args) ───────────────────────────────
    project_id: str,
    video_ids: list[str] | None = None,
) -> SearchResult:
    """
    Mode is inferred from arguments:
      nl_query=None, filters set  → Mode 1: structural (scroll + aggregation)
      nl_query set,  filters=None → Mode 2: pure semantic (hybrid BM + dense, then rerank)
      both set                    → Mode 3: hybrid (structural pre-filter, then semantic)
      both None                   → raises ValueError
    """
    mode = (
        "structural" if nl_query is None
        else "semantic" if filters is None
        else "hybrid"
    )
    
    qdrant_filter = _build_filter(project_id, video_ids, filters)
    
    if mode == "structural":
        return _structural_search(
            client=client,
            collection_name=settings.collection_name,
            qdrant_filter=qdrant_filter,
            operation=operation,
            group_by_field=group_by_field,
        )
    else:
        segments = _semantic_search(
            client=client,
            collection_name=settings.collection_name,
            nl_query=nl_query,
            search_vector=search_vector,
            project_id=project_id,
            qdrant_filter=qdrant_filter,
            top_k=top_k,
            prefetch_k=settings.prefetch_k,
            dense_embedder=dense_embedder,
            sparse_embedder=sparse_embedder,
            reranker=reranker,
            rerank_top_n=settings.rerank_top_n,
        )
        return SearchResult(
            mode=mode,
            operation="FETCH",
            total_count=len(segments),
            segments=segments,
            group_by_data=None,
        )
