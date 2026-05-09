import logging
from sentence_transformers import SentenceTransformer
from fastembed import TextEmbedding, SparseTextEmbedding, SparseEmbedding
from creator_joy.transcription.schema import VideoSegment

logger = logging.getLogger(__name__)

def timecode_to_seconds(timecode: str) -> float:
    """Convert 'MM:SS' to float seconds."""
    parts = timecode.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return 0.0

def build_production_description(seg: VideoSegment) -> str:
    """
    Flatten production metadata into a natural language sentence
    for the dense_production embedding vector.
    """
    parts = []

    shot = seg.frame.shot_type
    angle = seg.frame.camera_angle
    movement = seg.frame.camera_movement
    if shot not in ("[unclear]", ""):
        parts.append(f"{shot} shot")
    if angle not in ("[unclear]", ""):
        parts.append(f"{angle} angle")
    if movement not in ("static", "[unclear]", ""):
        parts.append(f"{movement} camera movement")

    bg = seg.background.type
    if bg not in ("[unclear]", ""):
        parts.append(f"{bg} background")

    light = seg.lighting.light_quality
    light_dir = seg.lighting.key_light_direction
    if light not in ("[unclear]", ""):
        parts.append(f"{light} lighting from {light_dir}")

    grade = seg.production_observables.color_grade_feel
    if grade not in ("[unclear]", ""):
        parts.append(f"{grade} color grade")

    mic = seg.production_observables.microphone_type_inferred
    if mic not in ("[unclear]", ""):
        parts.append(f"{mic} microphone")

    if seg.audio.music.present:
        genre = seg.audio.music.genre_feel
        if genre not in ("[unclear]", "none", ""):
            parts.append(f"{genre} background music")

    if seg.editing.cut_event.occurred:
        cut_type = seg.editing.cut_event.type or "cut"
        parts.append(f"{cut_type} edit")

    if seg.on_screen_text.present:
        parts.append("on-screen text overlay")
    if seg.graphics_and_animations.present:
        parts.append("graphics/animations")

    if not parts:
        return seg.observable_summary

    return ". ".join(parts).capitalize() + "."

class DenseEmbedder:
    def __init__(self, model_name: str, use_gpu: bool = True) -> None:
        self.model_name = model_name
        self.use_gpu = use_gpu
        self._model: SentenceTransformer | None = None

    def _load(self) -> SentenceTransformer:
        if self._model is None:
            device = "cuda" if self.use_gpu else "cpu"
            logger.debug("Loading dense embedding model %s on %s", self.model_name, device)
            self._model = SentenceTransformer(self.model_name, device=device)
        return self._model

    def encode_query(self, text: str) -> list[float]:
        model = self._load()
        vec = model.encode([text], prompt_name="query", normalize_embeddings=True)
        return vec[0].tolist()

    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vecs = model.encode(texts, prompt_name="document", normalize_embeddings=True,
                            batch_size=32, show_progress_bar=False)
        return [v.tolist() for v in vecs]

class SparseEmbedder:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: SparseTextEmbedding | None = None

    def _load(self) -> SparseTextEmbedding:
        if self._model is None:
            logger.debug("Loading sparse embedding model %s", self.model_name)
            self._model = SparseTextEmbedding(self.model_name)
        return self._model

    def encode(self, texts: list[str]) -> list[SparseEmbedding]:
        return list(self._load().embed(texts))

    def encode_query(self, text: str) -> SparseEmbedding:
        return self.encode([text])[0]
