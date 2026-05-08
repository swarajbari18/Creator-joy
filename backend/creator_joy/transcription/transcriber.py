from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import google.genai as genai
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import ValidationError

from creator_joy.ingestion.models import VideoRecord
from creator_joy.transcription.models import TranscriptionSettings
from creator_joy.transcription.schema import TranscriptionPayload

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a meticulous video documentarian. Your job is to observe and record everything in a video as structured data. \
You do not evaluate, judge, or interpret. You record only what is directly observable. \
When uncertain about any field, write [unclear]. When speech is inaudible, write [inaudible].\
"""

# Principle 3: Focus-on-Vision anchor (exact wording from multimodal-prompting-research.md)
_FOCUS_INSTRUCTION = """\
Look carefully and thoroughly at the actual content of this video. \
Base every field value on what you directly observe in this specific video, \
not on what you would expect a typical video of this type to contain. \
Do not record typical or assumed values. Only record what you can directly observe.\
"""

_FIELD_ROUTING = """\
Field instructions — observe only the correct modality for each field group:
- speech.transcript: verbatim spoken words from audio only — include um, uh, false starts, exact wording. Never paraphrase in the transcript field — verbatim only.
- speaker_id: identify the speaker using BOTH who is visibly speaking (lip movement, facing camera) AND voice characteristics. If these conflict, record [unclear].
- frame fields: observe only what is physically in the video frame
- background fields: observe only what is visible behind the subject
- lighting fields: observe only visible light sources and their observable effects
- on_screen_text: record only text visible in the frame — exact text, position, color, animation. Not spoken words.
- graphics_and_animations: record any visual elements added in post-production
- editing fields: record cut events and transition effects observable at segment boundaries
- audio fields: observe only non-speech audio — music, SFX, ambient
- production_observables: record only directly observable production details\
"""

_RULES = """\
Rules:
- Use MM:SS timecode format for all timecode fields
- Create a new segment entry whenever ANY observable element changes (new cut, speaker change, overlay appears, camera movement, music shift)
- Record segments in strict chronological order — each entry must correspond to a specific, verifiable moment in the video
- Record speech VERBATIM — include 'um', 'uh', false starts, and repeated words. Do not clean up or paraphrase.
- Write [unclear] for any field you cannot directly verify from observation
- Write [inaudible] for speech you cannot clearly hear
- Do not skip segments to save tokens — every observable event must be captured
- observable_summary: one short factual sentence describing what is physically happening in this specific segment\
"""


def _build_prompt(video_record: VideoRecord) -> str:
    title = video_record.title or "[unknown title]"
    creator = video_record.uploader or "[unknown creator]"
    schema_json = json.dumps(TranscriptionPayload.model_json_schema(), indent=2)

    return f"""{_FOCUS_INSTRUCTION}

Context: This video is titled "{title}" by "{creator}".

{_RULES}

{_FIELD_ROUTING}

Produce a Rich Video Transcription matching this exact JSON schema:
{schema_json}

OUTPUT JSON ONLY"""


def _parse_json_response(raw: str, llm: ChatGoogleGenerativeAI) -> dict:
    # Attempt 1: direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Attempt 2: strip markdown code block wrapper
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        # Remove first line (```json or ```) and last ``` if present
        inner_lines = lines[1:]
        if inner_lines and inner_lines[-1].strip() == "```":
            inner_lines = inner_lines[:-1]
        inner = "\n".join(inner_lines).strip()
        try:
            return json.loads(inner)
        except json.JSONDecodeError as second_error:
            last_error = second_error
    else:
        last_error = json.JSONDecodeError("", raw, 0)

    # Attempt 3: ask the LLM to fix the broken JSON
    logger.debug("JSON parse failed after 2 attempts — requesting LLM fix pass")
    fix_message = HumanMessage(content=(
        f"The following text should be valid JSON but failed to parse.\n"
        f"Error: {last_error}\n\n"
        f"Fix the JSON and return ONLY the corrected JSON, nothing else:\n\n{raw}"
    ))
    fixed_response = llm.invoke([fix_message])
    fixed_raw = fixed_response.content
    try:
        return json.loads(fixed_raw)
    except json.JSONDecodeError as final_error:
        raise RuntimeError(
            f"JSON parse failed after 3 attempts (direct, strip backticks, LLM fix).\n"
            f"Final error: {final_error}\n"
            f"Original raw response:\n{raw}\n"
            f"LLM-fixed response:\n{fixed_raw}"
        ) from final_error


class GeminiTranscriber:
    def __init__(self, settings: TranscriptionSettings) -> None:
        self.settings = settings
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY environment variable is not set")
        self._genai_client = genai.Client(api_key=api_key)
        self._llm = ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            temperature=settings.temperature,
            google_api_key=api_key,
        )
        logger.debug("GeminiTranscriber initialized model=%s temperature=%s", settings.gemini_model, settings.temperature)

    def transcribe(self, video_path: Path, video_record: VideoRecord) -> TranscriptionPayload:
        logger.debug("Starting transcription video_id=%s path=%s", video_record.id, video_path)
        if not video_path.exists():
            raise RuntimeError(f"Video file not found: {video_path}")

        uploaded_file = None
        try:
            uploaded_file = self._upload_and_wait(video_path)
            payload = self._call_gemini(uploaded_file.uri, video_record)
            return payload
        finally:
            if uploaded_file is not None:
                try:
                    self._genai_client.files.delete(name=uploaded_file.name)
                    logger.debug("Deleted uploaded Gemini file name=%s", uploaded_file.name)
                except Exception:
                    logger.warning("Failed to delete Gemini file name=%s — continuing", uploaded_file.name, exc_info=True)

    def _upload_and_wait(self, video_path: Path):
        logger.debug("Uploading video to Gemini File API path=%s", video_path)
        uploaded = self._genai_client.files.upload(file=str(video_path))
        logger.debug("Upload submitted file_name=%s state=%s", uploaded.name, uploaded.state)

        elapsed = 0
        while uploaded.state.name == "PROCESSING":
            logger.debug("Waiting for Gemini file processing elapsed=%ss file_name=%s", elapsed, uploaded.name)
            time.sleep(self.settings.file_poll_interval_seconds)
            elapsed += self.settings.file_poll_interval_seconds
            if elapsed >= self.settings.file_poll_timeout_seconds:
                raise RuntimeError(
                    f"Gemini file processing timed out after {elapsed}s for {video_path}. "
                    f"File name: {uploaded.name}"
                )
            uploaded = self._genai_client.files.get(name=uploaded.name)

        if uploaded.state.name != "ACTIVE":
            raise RuntimeError(
                f"Gemini file in unexpected state '{uploaded.state.name}' for {video_path}. "
                f"File name: {uploaded.name}"
            )

        logger.debug("Gemini file is ACTIVE file_name=%s uri=%s", uploaded.name, uploaded.uri)
        return uploaded

    def _call_gemini(self, file_uri: str, video_record: VideoRecord) -> TranscriptionPayload:
        prompt = _build_prompt(video_record)
        logger.debug("Invoking Gemini model=%s file_uri=%s", self.settings.gemini_model, file_uri)

        # Principle 1 (multimodal-prompting-research.md): media FIRST, instructions AFTER
        message = HumanMessage(content=[
            {"type": "media", "file_uri": file_uri, "mime_type": "video/mp4"},
            {"type": "text", "text": prompt},
        ])
        response = self._llm.invoke([SystemMessage(content=_SYSTEM_PROMPT), message])
        logger.debug("Gemini full response: %s", response)
        if isinstance(response.content, list):
            raw_text = "\n".join(
                block["text"] for block in response.content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        else:
            raw_text = response.content
        logger.debug("Gemini response received length=%s chars", len(raw_text))

        parsed = _parse_json_response(raw_text, self._llm)
        logger.debug("JSON parsed successfully")

        try:
            payload = TranscriptionPayload.model_validate(parsed)
        except ValidationError as exc:
            raise RuntimeError(
                f"Pydantic validation failed after JSON parse.\n"
                f"Validation error: {exc}\n"
                f"Parsed dict keys: {list(parsed.keys()) if isinstance(parsed, dict) else type(parsed)}"
            ) from exc

        logger.debug("Pydantic validation passed segments=%s", len(payload.segments))
        return payload
