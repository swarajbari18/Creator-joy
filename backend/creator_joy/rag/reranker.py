import logging
from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

class CrossEncoderReranker:
    def __init__(self, model_name: str, use_gpu: bool = True) -> None:
        self.model_name = model_name
        self.use_gpu = use_gpu
        self._model: CrossEncoder | None = None

    def _load(self) -> CrossEncoder:
        if self._model is None:
            device = "cuda" if self.use_gpu else "cpu"
            logger.debug("Loading reranker model %s on %s", self.model_name, device)
            self._model = CrossEncoder(self.model_name, device=device)
        return self._model

    def rerank(self, query: str, candidates: list[dict], top_n: int) -> list[dict]:
        """
        candidates: list of payload dicts from Qdrant
        Returns top_n candidates sorted by descending reranker score.
        Each returned dict has an extra "_rerank_score" key.
        """
        model = self._load()
        # Use transcript as the document text for reranking
        pairs = [(query, c.get("transcript", "") + " " + c.get("observable_summary", ""))
                 for c in candidates]
        scores = model.predict(pairs)
        for i, candidate in enumerate(candidates):
            candidate["_rerank_score"] = float(scores[i])
        ranked = sorted(candidates, key=lambda x: x["_rerank_score"], reverse=True)
        return ranked[:top_n]
