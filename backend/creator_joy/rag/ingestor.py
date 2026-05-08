import logging
import uuid
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client import models

from creator_joy.ingestion.database import IngestionDatabase
from creator_joy.transcription.schema import RichVideoTranscription, VideoSegment
from creator_joy.rag.models import RAGSettings
from creator_joy.rag.embedder import DenseEmbedder, SparseEmbedder, build_production_description, timecode_to_seconds

logger = logging.getLogger(__name__)

_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

def make_point_id(video_id: str, segment_id: int) -> str:
    """UUID5-based deterministic ID. Same video+segment always maps to same point."""
    return str(uuid.uuid5(_NAMESPACE, f"{video_id}:{segment_id}"))

def _build_payload(seg: VideoSegment, transcription: RichVideoTranscription, project_id: str) -> dict:
    return {
        # Identity
        "project_id":            project_id,
        "video_id":              seg.video_id,
        "segment_id":            seg.segment_id,
        "video_title":           transcription.title,
        "creator_name":          transcription.creator_name,
        "platform":              transcription.platform,
        "upload_date":           transcription.upload_date,

        # Timecode
        "timecode_start":        seg.timecode_start,
        "timecode_end":          seg.timecode_end,
        "timecode_start_seconds": timecode_to_seconds(seg.timecode_start),
        "timecode_end_seconds":  timecode_to_seconds(seg.timecode_end),
        "duration_seconds":      seg.duration_seconds,

        # Speech
        "transcript":            seg.speech.transcript,
        "speaker_id":            seg.speech.speaker_id,
        "speaker_visible":       seg.speech.speaker_visible,
        "language":              seg.speech.language,

        # Frame
        "shot_type":             seg.frame.shot_type,
        "camera_angle":          seg.frame.camera_angle,
        "camera_movement":       seg.frame.camera_movement,
        "depth_of_field":        seg.frame.depth_of_field,
        "subjects_in_frame":     seg.frame.subjects_in_frame,

        # Background
        "background_type":       seg.background.type,
        "background_description": seg.background.description,
        "background_elements":   seg.background.elements_visible,

        # Lighting
        "key_light_direction":   seg.lighting.key_light_direction,
        "light_quality":         seg.lighting.light_quality,
        "catch_light_in_eyes":   seg.lighting.catch_light_in_eyes,
        "color_temperature_feel": seg.lighting.color_temperature_feel,

        # On-screen text
        "on_screen_text_present": seg.on_screen_text.present,
        "on_screen_texts":       [e.text for e in seg.on_screen_text.entries],

        # Graphics
        "graphics_present":      seg.graphics_and_animations.present,

        # Editing
        "cut_occurred":          seg.editing.cut_event.occurred,
        "cut_type":              seg.editing.cut_event.type,
        "transition_effect":     seg.editing.transition_effect,
        "speed_change":          seg.editing.speed_change,

        # Audio
        "music_present":         seg.audio.music.present,
        "music_tempo_feel":      seg.audio.music.tempo_feel,
        "music_genre_feel":      seg.audio.music.genre_feel,
        "audio_quality":         seg.audio.audio_quality,

        # Production
        "microphone_type":       seg.production_observables.microphone_type_inferred,
        "color_grade_feel":      seg.production_observables.color_grade_feel,
        "wardrobe_notable":      seg.production_observables.wardrobe_notable,
        "props_in_use":          seg.production_observables.props_in_use,

        # Retrieval
        "observable_summary":    seg.observable_summary,
        "production_description": build_production_description(seg),
    }

class VideoIngestor:
    def __init__(
        self,
        settings: RAGSettings,
        ingestion_db: IngestionDatabase,
        dense_embedder: DenseEmbedder,
        sparse_embedder: SparseEmbedder,
        qdrant_client: QdrantClient,
    ) -> None:
        self.settings = settings
        self.ingestion_db = ingestion_db
        self.dense_embedder = dense_embedder
        self.sparse_embedder = sparse_embedder
        self.qdrant_client = qdrant_client

    def index_video(self, video_id: str) -> int:
        """
        Load transcription.json for video_id, embed all segments,
        upsert into Qdrant. Returns number of segments indexed.
        """
        video = self.ingestion_db.get_video(video_id)
        if not video:
            raise ValueError(f"Video {video_id} not found in database.")
        project_id = video.project_id

        # Find transcription.json via path convention
        transcription_path = self._find_transcription_path(video_id)
        transcription = RichVideoTranscription.model_validate_json(
            transcription_path.read_text(encoding="utf-8")
        )

        points = []
        transcript_texts = []
        production_texts = []
        for seg in transcription.segments:
            transcript_texts.append(seg.speech.transcript + " " + seg.observable_summary)
            production_texts.append(build_production_description(seg))

        dense_t_vecs = self.dense_embedder.encode_documents(transcript_texts)
        dense_p_vecs = self.dense_embedder.encode_documents(production_texts)
        sparse_vecs = self.sparse_embedder.encode(transcript_texts)

        for i, seg in enumerate(transcription.segments):
            payload = _build_payload(seg, transcription, project_id)
            sparse = sparse_vecs[i]
            point = models.PointStruct(
                id=make_point_id(video_id, seg.segment_id),
                vector={
                    "dense_transcript": dense_t_vecs[i],
                    "dense_production": dense_p_vecs[i],
                    "sparse_minicoil": models.SparseVector(
                        indices=sparse.indices,
                        values=sparse.values,
                    ),
                },
                payload=payload,
            )
            points.append(point)

        self.qdrant_client.upsert(
            collection_name=self.settings.collection_name,
            points=points,
        )
        logger.debug("Indexed %s segments for video_id=%s", len(points), video_id)
        return len(points)

    def _find_transcription_path(self, video_id: str) -> Path:
        video = self.ingestion_db.get_video(video_id)
        conventional = (
            self.settings.storage_root
            / "projects"
            / video.project_id
            / "videos"
            / video_id
            / "transcription.json"
        )
        if conventional.exists():
            return conventional
            
        raise RuntimeError(
            f"transcription.json not found for video_id={video_id}. "
            "Run transcription first."
        )
