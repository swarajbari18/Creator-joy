import json
import logging
from typing import AsyncGenerator, Dict, Any
from langchain_core.messages import HumanMessage
from creator_joy.chat.memory import ChatMemory, build_message_history
from creator_joy.chat.agent import create_orchestrator, _make_orchestrator_llm
from creator_joy.ingestion.database import IngestionDatabase
from creator_joy.rag.models import RAGSettings
from creator_joy.engagement.formatter import format_metrics_for_system_prompt
from creator_joy.chat.prompts import build_orchestrator_system_prompt

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.memory = ChatMemory(db_path)
        self.ingestion_db = IngestionDatabase(RAGSettings().database_path)

    def _load_engagement_data(self, videos: list) -> list[dict]:
        """
        Converts VideoRecord objects to dicts and parses engagement_metrics JSON.
        view_count / like_count / comment_count come from the yt-dlp metadata JSON
        that ingestion already wrote to disk at v.metadata_path.
        """
        from pathlib import Path

        video_dicts = []
        for v in videos:
            metrics = {}
            if v.engagement_metrics:
                try:
                    metrics = json.loads(v.engagement_metrics)
                except Exception:
                    logger.error("Failed to parse engagement metrics for video %s", v.id)

            yt_meta = {}
            if v.metadata_path:
                try:
                    yt_meta = json.loads(Path(v.metadata_path).read_text(encoding="utf-8"))
                except Exception:
                    logger.warning("Could not load yt-dlp metadata for video %s", v.id)

            video_dicts.append({
                "id": v.id,
                "title": v.title,
                "role": v.role,
                "uploader": v.uploader,
                "platform": v.platform,
                "source_url": v.source_url,
                "view_count": yt_meta.get("view_count"),
                "like_count": yt_meta.get("like_count"),
                "comment_count": yt_meta.get("comment_count"),
                "duration_seconds": v.duration,
                "video_age_days": metrics.get("video_age_days"),
                "er_views": metrics.get("er_views"),
                "channel_follower_count": metrics.get("channel_follower_count"),
                "heatmap_peak_intensity": metrics.get("heatmap_peak_intensity"),
            })
        return video_dicts

    async def stream_response(
        self,
        project_id: str,
        session_id: str,
        user_message: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Async generator yielding SSE event dicts.
        """
        logger.info("Starting chat stream project_id=%s session_id=%s", project_id, session_id)
        
        # 1. Load video manifest for this project
        videos = self.ingestion_db.list_project_videos(project_id)
        video_ids = [v.id for v in videos]
        logger.debug("Loaded %s videos for project", len(video_ids))
        
        # 2. Load engagement metrics (pre-computed in SQLite)
        engagement_data = self._load_engagement_data(videos)
        
        # 3. Build system prompt
        engagement_block = format_metrics_for_system_prompt(engagement_data)
        system_prompt = build_orchestrator_system_prompt(
            project_manifest=videos,
            engagement_block=engagement_block,
        )
        logger.debug("System prompt built, length=%s", len(system_prompt))
        
        # 4. Load conversation history
        history = self.memory.load_history(session_id, max_turns=15)
        history_messages = build_message_history(history)
        logger.debug("Loaded %s history messages", len(history_messages))
        
        # 5. Persist user message
        turn_number = len(history) // 2 + 1
        self.memory.save_turn(project_id, session_id, turn_number, "user", user_message)
        
        # 6. Create orchestrator for this session
        orchestrator = create_orchestrator(project_id, video_ids, system_prompt)
        
        # 7. Build full message list for this invocation
        messages = history_messages + [HumanMessage(content=user_message)]
        
        # 8. Stream events
        full_response = ""
        tool_calls_this_turn = []
        
        logger.info("Invoking orchestrator agent")
        async for event in orchestrator.astream_events(
            {"messages": messages},
            version="v2",
        ):
            event_type = event["event"]
            
            if event_type == "on_custom_event":
                # Events from get_stream_writer() inside tools
                data = event["data"]
                yield data
            
            elif event_type == "on_chat_model_stream":
                # Final synthesis tokens
                chunk = event["data"]["chunk"]
                # chunk.content might be empty if it's a tool call chunk
                if chunk.content:
                    full_response += chunk.content
                    yield {"type": "token", "content": chunk.content}
            
            elif event_type == "on_chat_model_end":
                # Fallback: capture complete response when streaming produced no tokens
                if not full_response:
                    output = event["data"].get("output")
                    if output and not getattr(output, "tool_calls", None):
                        content = output.content if isinstance(output.content, str) else ""
                        if content:
                            full_response = content
                            yield {"type": "token", "content": content}

            elif event_type == "on_tool_start":
                if event["name"] == "use_sub_agent_with_skill":
                    inputs = event["data"]["input"]
                    tool_calls_this_turn.append(inputs)
            
            elif event_type == "on_tool_end":
                if event["name"] == "use_sub_agent_with_skill":
                    # Persist tool_call and tool_return to SQLite
                    call_data = tool_calls_this_turn[-1] if tool_calls_this_turn else {}
                    self.memory.save_turn(
                        project_id, session_id, turn_number, "tool_call",
                        json.dumps(call_data),
                        skill_name=call_data.get("skill_name"),
                    )
                    self.memory.save_turn(
                        project_id, session_id, turn_number, "tool_return",
                        str(event["data"]["output"]),
                    )
        
        # 9. Persist final synthesized response
        if full_response:
            self.memory.save_turn(
                project_id, session_id, turn_number, "assistant", full_response
            )
        
        # 10. Compact memory if needed
        await self.memory.compact_if_needed(
            session_id, threshold_turns=20, keep_recent=10, llm=_make_orchestrator_llm()
        )
        
        yield {"type": "done"}
