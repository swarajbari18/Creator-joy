import logging
from qdrant_client import QdrantClient, models

from creator_joy.rag.models import RAGSettings, IndexRecord, IndexStatus, SearchResult, StructuralFilters
from creator_joy.rag.database import RAGDatabase
from creator_joy.rag.collection import ensure_collection
from creator_joy.rag.embedder import DenseEmbedder, SparseEmbedder
from creator_joy.rag.reranker import CrossEncoderReranker
from creator_joy.rag.ingestor import VideoIngestor
from creator_joy.rag.retriever import search_segments
from creator_joy.ingestion.database import IngestionDatabase

logger = logging.getLogger(__name__)

class RAGService:
    def __init__(self, settings: RAGSettings | None = None) -> None:
        self.settings = settings or RAGSettings()
        logger.debug("Creating RAGService settings=%s", self.settings)
        self.settings.storage_root.mkdir(parents=True, exist_ok=True)

        self.ingestion_db = IngestionDatabase(self.settings.database_path)
        self.rag_db = RAGDatabase(self.settings.database_path)

        self.qdrant_client = QdrantClient(
            host=self.settings.qdrant_host,
            port=self.settings.qdrant_port,
        )
        ensure_collection(
            self.qdrant_client,
            self.settings.collection_name,
            self.settings.embedding_dim,
        )

        self.dense_embedder = DenseEmbedder(
            self.settings.embedding_model, self.settings.use_gpu
        )
        self.sparse_embedder = SparseEmbedder(self.settings.sparse_model)
        self.reranker = CrossEncoderReranker(
            self.settings.reranker_model, self.settings.use_gpu
        )
        self.ingestor = VideoIngestor(
            settings=self.settings,
            ingestion_db=self.ingestion_db,
            dense_embedder=self.dense_embedder,
            sparse_embedder=self.sparse_embedder,
            qdrant_client=self.qdrant_client,
        )

    def index_video(self, video_id: str) -> IndexRecord:
        video = self.ingestion_db.get_video(video_id)
        if video is None:
            raise ValueError(f"Video not found: {video_id}")

        record = self.rag_db.create_or_reset_index(
            video_id=video_id,
            project_id=video.project_id,
            collection_name=self.settings.collection_name,
        )
        self.rag_db.update_index_status(record.id, IndexStatus.PROCESSING)

        try:
            count = self.ingestor.index_video(video_id)
            
            # Verify that points actually made it into Qdrant
            qdrant_count = self.qdrant_client.count(
                collection_name=self.settings.collection_name,
                count_filter=models.Filter(
                    must=[models.FieldCondition(key="video_id", match=models.MatchValue(value=video_id))]
                )
            ).count
            
            if qdrant_count == 0 and count > 0:
                raise RuntimeError(
                    f"Indexing reported {count} segments processed, but Qdrant collection "
                    f"'{self.settings.collection_name}' still has 0 points for video {video_id}. "
                    "Check if Qdrant is out of disk space or if the docker volume is read-only."
                )

            self.rag_db.update_index_status(
                record.id, IndexStatus.COMPLETED, segments_indexed=qdrant_count
            )
        except Exception as exc:
            logger.exception("RAG indexing failed video_id=%s", video_id)
            self.rag_db.update_index_status(record.id, IndexStatus.FAILED, error_message=str(exc))
            raise

        completed = self.rag_db.get_index(record.id)
        if completed is None:
            raise RuntimeError(f"Completed index row disappeared: {record.id}")
        return completed

    def search(
        self,
        project_id: str,
        video_ids: list[str] | None = None,
        filters: StructuralFilters | None = None,
        operation: str = "FETCH",
        group_by_field: str | None = None,
        nl_query: str | None = None,
        search_vector: str = "dense_transcript",
        top_k: int = 10,
    ) -> SearchResult:
        # Before searching, verify that the requested videos actually have data in Qdrant
        if video_ids:
            for v_id in video_ids:
                count = self.qdrant_client.count(
                    collection_name=self.settings.collection_name,
                    count_filter=models.Filter(
                        must=[models.FieldCondition(key="video_id", match=models.MatchValue(value=v_id))]
                    )
                ).count
                if count == 0:
                    logger.warning(
                        "SILENT FAILURE DETECTED: Video %s is requested for search but has 0 points in Qdrant collection '%s'. "
                        "The index might have been lost (e.g. Docker restart without persistence).",
                        v_id, self.settings.collection_name
                    )

        return search_segments(
            project_id=project_id,
            video_ids=video_ids,
            filters=filters,
            operation=operation,  # type: ignore
            group_by_field=group_by_field,
            nl_query=nl_query,
            search_vector=search_vector,  # type: ignore
            top_k=top_k,
            client=self.qdrant_client,
            dense_embedder=self.dense_embedder,
            sparse_embedder=self.sparse_embedder,
            reranker=self.reranker,
            settings=self.settings,
        )
