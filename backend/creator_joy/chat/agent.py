import os
import json
import logging
from typing import List, Any
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)


class SubAgentCallArgs(BaseModel):
    skill_name: str = Field(
        description=(
            "Name of the skill to invoke. Available skills: "
            "search_skill (direct data retrieval), "
            "HookDiagnosis, TwoVideoComparison, RetentionDiagnosis, ScriptAnalysis, "
            "SingleVideoAnalysis, ProductionAudit, EditingAnalysis, CompetitorIntelligence, "
            "SeriesAnalysis, OverlayAudit, AudioAnalysis, EngagementCorrelation, "
            "ShortFormOptimization."
        )
    )
    situational_prompt: str = Field(
        description=(
            "Detailed briefing for the sub-agent. Must include: user goal, "
            "prior findings (distilled), current specific task, video UUIDs in scope, "
            "and why this sub-agent is being called. Do NOT include expected output format."
        )
    )


def _make_orchestrator_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=1.0,
        thinking_budget=0,
        max_output_tokens=8192,
        max_retries=3,
    )


def _make_sub_agent_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=1.0,
        thinking_budget=0,
        max_output_tokens=4096,
        max_retries=2,
    )


def make_skill_tool(project_id: str, video_ids: list[str]):
    """
    Returns the use_sub_agent_with_skill tool bound to the current session context.
    """
    from creator_joy.chat.tools import search_segments, retrieve, SubAgentContext  # noqa: F401
    
    @tool(args_schema=SubAgentCallArgs)
    async def use_sub_agent_with_skill(skill_name: str, situational_prompt: str) -> str:
        """
        Delegate a specific sub-task to a specialized skill sub-agent.
        """
        from creator_joy.chat.registry import SKILLS
        from langchain_core.callbacks import adispatch_custom_event

        if skill_name not in SKILLS:
            logger.warning("Sub-agent call with unknown skill: %s", skill_name)
            return f"Error: unknown skill '{skill_name}'. Available: {list(SKILLS.keys())}"

        skill = SKILLS[skill_name]
        logger.info("Invoking sub-agent skill=%s", skill_name)
        logger.debug("Situational prompt: %s", situational_prompt)

        # get_stream_writer() is broken for async tools (LangGraph bug #6447).
        # adispatch_custom_event works correctly in async tools and emits
        # on_custom_event in the parent's astream_events stream.
        await adispatch_custom_event("skill_start", {
            "skill": skill_name,
            "message": f"Using {skill_name}...",
        })
        
        context = SubAgentContext(
            project_id=project_id,
            video_ids=video_ids,
            skill_prompt=skill.prompt,
        )
        
        try:
            if skill.category == "search":
                logger.debug("Running search category sub-agent")
                agent = create_react_agent(
                    model=_make_sub_agent_llm(),
                    tools=[search_segments],
                    prompt=skill.prompt,
                    context_schema=SubAgentContext,
                )
                result = await agent.ainvoke(
                    {"messages": [HumanMessage(content=situational_prompt)]},
                    context=context,
                    config={"recursion_limit": 10},
                )

            elif skill.category == "pre_injected":
                logger.debug("Running pre_injected category sub-agent")
                pre_fetched = await skill.prefetch_fn(project_id, video_ids, situational_prompt)
                enriched_message = (
                    f"{situational_prompt}\n\n"
                    f"--- PRE-FETCHED SEGMENT DATA ---\n"
                    f"{pre_fetched}"
                )
                agent = create_react_agent(
                    model=_make_sub_agent_llm(),
                    tools=[],
                    prompt=skill.prompt,
                    context_schema=SubAgentContext,
                )
                result = await agent.ainvoke(
                    {"messages": [HumanMessage(content=enriched_message)]},
                    context=context,
                    config={"recursion_limit": 10},
                )

            else:  # "dynamic"
                logger.debug("Running dynamic category sub-agent")
                agent = create_react_agent(
                    model=_make_sub_agent_llm(),
                    tools=[retrieve],
                    prompt=skill.prompt,
                    context_schema=SubAgentContext,
                )
                result = await agent.ainvoke(
                    {"messages": [HumanMessage(content=situational_prompt)]},
                    context=context,
                    config={"recursion_limit": 10},
                )
            
            output = result["messages"][-1].content
            logger.info("Sub-agent %s completed successfully", skill_name)
            await adispatch_custom_event("skill_complete", {"skill": skill_name})
            return output

        except Exception as e:
            logger.exception("Error in sub-agent %s", skill_name)
            await adispatch_custom_event("skill_error", {"skill": skill_name, "error": str(e)})
            return f"Skill '{skill_name}' encountered an error: {str(e)}"
    
    return use_sub_agent_with_skill


def create_orchestrator(
    project_id: str,
    video_ids: list[str],
    system_prompt: str,
):
    """
    Create the main orchestrator agent for a session.
    """
    skill_tool = make_skill_tool(project_id, video_ids)
    llm = _make_orchestrator_llm()
    
    return create_react_agent(
        model=llm,
        tools=[skill_tool],
        prompt=system_prompt,
    )
