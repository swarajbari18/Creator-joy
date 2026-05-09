# Multi-Agent Architecture Research: CreatorJoy Chatbot Implementation Reference

**Date:** May 2026  
**Scope:** LangGraph multi-agent patterns, context passing, dynamic agent creation, tool runtime injection, streaming, and failure modes — specific to the CreatorJoy orchestrator + skill-based sub-agent design.

---

## Table of Contents

1. [Architecture Overview: What We're Building](#1-architecture-overview)
2. [LangGraph Patterns Relevant to Our Design](#2-langgraph-patterns)
3. [Context Passing: Orchestrator to Sub-Agent](#3-context-passing)
4. [Dynamic Agent Creation](#4-dynamic-agent-creation)
5. [LangChain RunnableConfig + ToolRuntime: Runtime Injection](#5-tool-runtime-injection)
6. [Streaming: Tool-Use Events to the User](#6-streaming)
7. [Known Failure Modes and How to Avoid Them](#7-failure-modes)
8. [Specific Recommendations for Our Architecture](#8-recommendations)
9. [Sources](#9-sources)

---

## 1. Architecture Overview

The system we are building follows the **Orchestrator-Subagent** pattern as described by Anthropic: a lead (main) agent decomposes tasks and delegates bounded work to specialists, with each subagent operating inside its own isolated context window and returning distilled findings.

```
User Message
     │
     ▼
Main Orchestrator (Gemini)
  ├── System prompt: skill catalog + engagement metrics pre-injected
  ├── Conversation history from SQLite
  └── Tool: use_sub_agent_with_skill(skill_name, situational_prompt)
              │
              ▼
        [Dynamic sub-agent created per call]
        Sub-Agent (LangChain ReAct)
          ├── System prompt = skill.md contents
          ├── Human message = situational_prompt from orchestrator
          ├── Tools (e.g., Qdrant search, analytics queries)
          └── project_id, video_ids injected at tool runtime
                              │
                              ▼
                    Returns findings to main agent
```

This is architecturally closest to **LangGraph's supervisor pattern** but implemented with dynamic agent instantiation (new agent per tool call) rather than a persistent compiled graph. The tradeoffs of this choice are examined in Section 4.

---

## 2. LangGraph Patterns Relevant to Our Design

### 2.1 The Supervisor Pattern

LangGraph's supervisor is a centralized routing node that receives every message, classifies intent, and directs it to specialist agents. Control returns to the supervisor after each specialist responds.

The `langgraph-supervisor` package provides the official implementation:

```python
from langgraph_supervisor import create_supervisor, create_handoff_tool
from langgraph.prebuilt import create_react_agent
from langchain_google_genai import ChatGoogleGenerativeAI

# Define specialist agents
search_agent = create_react_agent(
    model=ChatGoogleGenerativeAI(model="gemini-2.0-flash"),
    tools=[qdrant_search_tool, rerank_tool],
    name="search_specialist",
    prompt="You are a search specialist. Use the provided tools to find relevant content..."
)

analysis_agent = create_react_agent(
    model=ChatGoogleGenerativeAI(model="gemini-2.0-flash"),
    tools=[engagement_analysis_tool, trend_tool],
    name="analysis_specialist",
    prompt="You are an analytics specialist. Analyze engagement patterns..."
)

# Supervisor wraps them
supervisor = create_supervisor(
    agents=[search_agent, analysis_agent],
    model=ChatGoogleGenerativeAI(model="gemini-2.0-pro"),
    prompt=(
        "You are a CreatorJoy assistant. You have access to search and analytics specialists. "
        "Route tasks to the appropriate specialist based on what the creator needs."
    )
)

app = supervisor.compile()
```

**Key state structure** — the `MessagesState` base with custom append-only fields:

```python
from langgraph.graph import MessagesState
import operator
from typing import Annotated

class CreatorJoyState(MessagesState):
    current_skill: str
    findings: Annotated[list[str], operator.add]  # append-only, safe across agents
    engagement_metrics: dict                        # pre-injected, read-only
```

The `operator.add` reducer is critical: it lets multiple sub-agents append findings without overwriting each other — essential for audit trails and preventing routing loops.

### 2.2 Supervisor vs. Swarm: Choosing the Right Pattern

| Metric | Supervisor | Swarm |
|--------|-----------|-------|
| Single-domain latency | ~4.2s | ~2.8s |
| Multi-domain latency | ~9.1s | ~5.4s |
| LLM calls (single-domain) | 2 | 1 |
| LLM calls (multi-domain) | 4 | 2 |
| Routing accuracy | 94% | 91% |

**Decision:** Use the supervisor pattern (and the equivalent dynamic creation approach we've chosen). Rationale:
- Our main orchestrator needs **centralized context** (engagement metrics, conversation history, what's been discovered)
- Skill routing changes as we add new skills — centralized routing is easier to update
- We need audit trails (what skills were called, in what order, with what findings)
- Sub-agents don't need to coordinate peer-to-peer; all synthesis happens at the orchestrator

### 2.3 Dynamic System Prompts with `create_react_agent`

Our sub-agents need their system prompt set per-invocation (= skill.md content). `create_react_agent` natively supports this via a callable `prompt` parameter:

```python
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime
from dataclasses import dataclass

@dataclass
class SubAgentContext:
    project_id: str
    video_ids: list[str]
    skill_prompt: str  # contents of skill.md

def build_system_prompt(state, runtime: Runtime[SubAgentContext]) -> list:
    """Dynamically build system prompt from skill.md contents injected at runtime."""
    return [SystemMessage(content=runtime.context.skill_prompt)]

def create_skill_agent(tools: list, context: SubAgentContext):
    return create_react_agent(
        model=ChatGoogleGenerativeAI(model="gemini-2.0-flash"),
        tools=tools,
        prompt=build_system_prompt,      # callable — receives full state + runtime
        context_schema=SubAgentContext,  # defines the injected context type
    )
```

**Critical detail:** `create_react_agent` v2 (the default since late 2025) accepts `context_schema` — a TypedDict or dataclass that gets injected as `runtime.context` in prompt callables AND in tools. This is the primary mechanism for passing `project_id` and `video_ids` without the LLM seeing or controlling them.

### 2.4 Hierarchical State Passing via Subgraphs

When building with full LangGraph (rather than dynamic creation), subgraphs are the recommended pattern for nested agent systems:

```python
from langgraph.graph import StateGraph, START, END

# Sub-agent as a compiled subgraph
sub_graph = StateGraph(SubAgentState)
sub_graph.add_node("agent", sub_agent_node)
sub_graph.add_node("tools", tool_node)
sub_graph.add_edge(START, "agent")
sub_graph.add_conditional_edges("agent", route_tools)
sub_graph.add_edge("tools", "agent")
compiled_sub = sub_graph.compile()

# Main graph embeds the sub-graph as a node
main_graph = StateGraph(MainState)
main_graph.add_node("orchestrator", orchestrator_node)
main_graph.add_node("search_skill", compiled_sub)  # subgraph as node
```

State can be passed into subgraphs via shared state keys or through explicit input transformation nodes. This is the persistent-graph alternative to our dynamic creation approach.

---

## 3. Context Passing: Orchestrator to Sub-Agent

This is the hardest problem in the design. The wrong approach (dumping full conversation history) kills sub-agent quality; the right approach gives the sub-agent exactly what it needs to do its specific job.

### 3.1 The Situational Prompt Pattern (Our Core Design)

A **situational prompt** is a structured briefing written by the orchestrator that answers:
1. What is the overall goal of this conversation?
2. What has already been discovered/done by previous sub-agents?
3. What specifically do I need THIS sub-agent to find/do right now?
4. Why is this sub-agent being called (what gap are we filling)?

**Do NOT include in the situational prompt:**
- The raw conversation history (too much noise)
- Prescriptive output format instructions (kills quality per our design constraint)
- Information irrelevant to this sub-agent's specific task

**Do include:**
- A distilled summary of prior findings (150-300 tokens max)
- The specific question or task
- Any constraints (e.g., "focus only on videos from last 90 days")
- Relevant domain context (e.g., the creator's niche, audience size)

**Example situational prompt template:**

```python
def build_situational_prompt(
    overall_goal: str,
    prior_findings: list[str],
    current_task: str,
    why_this_agent: str,
) -> str:
    prior_summary = "\n".join(f"- {f}" for f in prior_findings) if prior_findings else "None yet."
    
    return f"""## Overall Goal
{overall_goal}

## What Has Been Discovered So Far
{prior_summary}

## Your Current Task
{current_task}

## Why You Are Being Called
{why_this_agent}"""
```

### 3.2 Context Compression Strategies

Anthropic's multi-agent research team found: **token usage explains 80% of performance variance** in complex agent tasks. Loading too much context onto a sub-agent causes non-linear performance decline.

Strategies ranked by effectiveness:

**1. Distillation (best):** The orchestrator LLM generates a compressed summary of prior sub-agent findings before passing them forward. Reduces context by 70-90% vs. raw forwarding.

```python
async def compress_findings(findings: list[str], llm) -> str:
    """Compress prior findings to ~150 tokens for sub-agent briefing."""
    if not findings:
        return "No prior findings."
    
    combined = "\n".join(findings)
    response = await llm.ainvoke([
        SystemMessage(content="Summarize these research findings in 2-3 bullet points, preserving key facts."),
        HumanMessage(content=combined)
    ])
    return response.content
```

**2. Selective inclusion:** Only pass findings that are relevant to the current sub-agent's domain. A search sub-agent doesn't need analysis findings; an analysis sub-agent does need the search findings.

**3. Structured flags over prose:** Use structured data snippets instead of narrated history:

```python
# BAD: prose history (tokens expensive, hard to parse)
prior_context = "The user asked about their views, and we found that views dropped in March..."

# GOOD: structured flags
prior_context = {
    "engagement_data_retrieved": True,
    "time_period": "last_90_days",
    "key_finding": "views_dropped_march_2026",
    "hypothesis_to_test": "title_quality_correlation"
}
```

**4. External memory:** For conversations that span many turns, persist findings to SQLite (which we already have) and selectively retrieve relevant findings per sub-agent call:

```python
async def get_relevant_prior_findings(
    conversation_id: str, 
    skill_name: str,
    db: sqlite3.Connection
) -> list[str]:
    """Retrieve only findings relevant to the current skill from SQLite."""
    cursor = db.execute(
        "SELECT finding FROM agent_findings WHERE conversation_id=? AND relevant_skills LIKE ?",
        (conversation_id, f'%{skill_name}%')
    )
    return [row[0] for row in cursor.fetchall()]
```

### 3.3 What NOT to Do

- **Never forward full message history** to a sub-agent. The sub-agent will hallucinate responses to previous turns, lose focus on its specific task, and burn tokens on irrelevant context.
- **Never pass raw tool outputs** from one sub-agent to the next without distillation. Tool outputs (e.g., full Qdrant search results) can be thousands of tokens. Pass the interpreted finding, not the raw data.
- **Never let the orchestrator summarize in its system prompt.** The system prompt is for skills/roles. Conversation-specific state goes in the human/assistant turn or in the situational prompt.

### 3.4 Conversation History Management

The orchestrator maintains full conversation history (stored in SQLite). But what gets passed into the orchestrator's context window must also be managed:

```python
from langchain_core.messages import trim_messages, AIMessage, HumanMessage

def prepare_orchestrator_messages(
    history: list[dict], 
    max_tokens: int = 4000
) -> list:
    """Trim conversation history to fit orchestrator context budget."""
    messages = [
        HumanMessage(content=m["content"]) if m["role"] == "user" 
        else AIMessage(content=m["content"]) 
        for m in history
    ]
    
    return trim_messages(
        messages,
        max_tokens=max_tokens,
        token_counter=len,       # replace with actual token counter
        strategy="last",         # keep most recent
        start_on="human",        # ensure we start on human turn
        include_system=True,
    )
```

---

## 4. Dynamic Agent Creation

### 4.1 The Pattern We're Using

We dynamically create a new LangChain agent instance every time `use_sub_agent_with_skill()` is called. This is **intentional** and supported — here's the complete implementation pattern:

```python
from langgraph.prebuilt import create_react_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from dataclasses import dataclass
from typing import Any

# Skill registry: maps skill_name -> (skill_prompt, tools)
SKILL_REGISTRY: dict[str, dict] = {}

def register_skill(name: str, prompt_path: str, tools: list):
    with open(prompt_path, "r") as f:
        skill_prompt = f.read()
    SKILL_REGISTRY[name] = {"prompt": skill_prompt, "tools": tools}

@dataclass
class SubAgentContext:
    project_id: str
    video_ids: list[str]

async def use_sub_agent_with_skill(
    skill_name: str,
    situational_prompt: str,
    project_id: str,
    video_ids: list[str],
) -> str:
    """
    Dynamically create a sub-agent with the given skill and invoke it.
    project_id and video_ids are injected at this layer — never passed by the LLM.
    """
    if skill_name not in SKILL_REGISTRY:
        raise ValueError(f"Unknown skill: {skill_name}")
    
    skill = SKILL_REGISTRY[skill_name]
    
    # Build system prompt callable that reads skill.md content
    def make_prompt(state, runtime):
        return [SystemMessage(content=runtime.context.prompt)]
    
    # Create agent fresh per call
    agent = create_react_agent(
        model=ChatGoogleGenerativeAI(model="gemini-2.0-flash"),
        tools=skill["tools"],
        prompt=make_prompt,
        context_schema=type("SkillContext", (), {
            "__annotations__": {"prompt": str, "project_id": str, "video_ids": list}
        }),
    )
    
    # Invoke with runtime context injected (project_id and video_ids never touch LLM)
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=situational_prompt)]},
        context={
            "prompt": skill["prompt"],
            "project_id": project_id,
            "video_ids": video_ids,
        }
    )
    
    # Return the last assistant message as the finding
    return result["messages"][-1].content
```

### 4.2 Dynamic Creation vs. Agent Pool

**Dynamic creation (what we're doing):**

Pros:
- Clean isolation: each invocation starts fresh, no state leak between calls
- Simpler code: no pool management, no agent reuse logic
- Per-call context injection is straightforward
- Works naturally with per-call skill.md system prompts

Cons:
- Slightly higher initialization overhead per call (~50-100ms for model client setup)
- No warm caching of compiled graph structures

**Agent pool (persistent agents, pre-compiled):**

Pros:
- Lower per-call latency for the compiled graph
- Can maintain within-session state per agent type

Cons:
- Complex: need to manage pool lifecycle, reset state between calls
- State leaks between calls if not carefully managed
- Harder to inject per-call context (project_id, video_ids) safely
- Premature optimization — the initialization cost is negligible vs. LLM latency

**Verdict:** Dynamic creation is the correct choice for our use case. The overhead is dominated by LLM inference time (seconds), not agent initialization (milliseconds). The isolation benefits far outweigh the marginal performance cost.

### 4.3 Caching the Compiled Graph (Hybrid Approach)

If initialization cost becomes measurable, cache the compiled graph but inject context per-invocation:

```python
from functools import lru_cache
from langgraph.prebuilt import create_react_agent

@lru_cache(maxsize=None)
def get_compiled_agent(skill_name: str):
    """Cache compiled graph per skill. Context injected at invoke time."""
    skill = SKILL_REGISTRY[skill_name]
    
    agent = create_react_agent(
        model=ChatGoogleGenerativeAI(model="gemini-2.0-flash"),
        tools=tuple(skill["tools"]),  # must be hashable for lru_cache
        context_schema=SubAgentContext,
    )
    return agent.compile()

async def invoke_skill(skill_name: str, situational_prompt: str, context: SubAgentContext):
    agent = get_compiled_agent(skill_name)
    return await agent.ainvoke(
        {"messages": [HumanMessage(content=situational_prompt)]},
        context=context,  # injected fresh each call
    )
```

This gives the best of both: compiled graph is cached (eliminates initialization overhead), but runtime context is fresh per call.

---

## 5. Tool Runtime Injection (LangChain RunnableConfig + ToolRuntime)

This is the mechanism that lets us inject `project_id`, `video_ids`, etc. into tool functions without the LLM ever seeing or controlling these values.

### 5.1 The ToolRuntime Approach (Recommended — LangGraph 0.6+)

`ToolRuntime` is a class in `langgraph.prebuilt` that is automatically injected into tools when they declare it as a parameter. It is completely hidden from the LLM's tool schema.

```python
from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from dataclasses import dataclass
from typing import Optional

@dataclass
class CreatorContext:
    project_id: str
    video_ids: list[str]
    creator_channel_id: str

@tool
def search_video_transcripts(
    query: str,
    top_k: int = 5,
    runtime: ToolRuntime = None,  # HIDDEN from LLM — auto-injected
) -> list[dict]:
    """Search for relevant segments in video transcripts using semantic search.
    
    Args:
        query: The search query to find relevant transcript segments
        top_k: Number of results to return
    """
    # Access injected context — LLM never sees or passes these
    project_id = runtime.context.project_id
    video_ids = runtime.context.video_ids
    
    # Use them in your tool logic
    results = qdrant_client.search(
        collection_name=f"transcripts_{project_id}",
        query_vector=embed(query),
        query_filter={"video_id": {"$in": video_ids}},
        limit=top_k,
    )
    return [{"text": r.payload["text"], "video_id": r.payload["video_id"]} for r in results]


@tool
def get_engagement_metrics(
    video_id: Optional[str] = None,
    runtime: ToolRuntime = None,  # HIDDEN from LLM
) -> dict:
    """Get engagement metrics for a video or the full channel.
    
    Args:
        video_id: Specific video ID, or None to get channel-wide metrics
    """
    project_id = runtime.context.project_id
    
    # If no video_id given, use the injected ones
    target_ids = [video_id] if video_id else runtime.context.video_ids
    
    return fetch_metrics_from_db(project_id, target_ids)
```

**How it flows:**

```python
# At agent creation time, set context_schema
agent = create_react_agent(
    model=...,
    tools=[search_video_transcripts, get_engagement_metrics],
    context_schema=CreatorContext,
)

# At invocation time, inject the actual values
result = await agent.ainvoke(
    {"messages": [HumanMessage(content=situational_prompt)]},
    context=CreatorContext(
        project_id="proj_abc123",
        video_ids=["vid_1", "vid_2", "vid_3"],
        creator_channel_id="UCxxxx",
    )
)
```

The LLM's tool schema for `search_video_transcripts` only shows `query` and `top_k`. It never knows `project_id` or `video_ids` exist.

### 5.2 The RunnableConfig Approach (Pre-0.6 / LangChain Without LangGraph)

If you are using LangChain tools outside LangGraph (or on older versions), use `RunnableConfig`:

```python
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

@tool
def search_transcripts_v1(
    query: str,
    config: RunnableConfig,  # auto-injected, hidden from LLM
) -> list[dict]:
    """Search video transcripts."""
    # Access via config["configurable"]
    project_id = config["configurable"]["project_id"]
    video_ids = config["configurable"]["video_ids"]
    
    return qdrant_search(query, project_id, video_ids)

# At invocation:
agent_executor.invoke(
    {"input": "find mentions of thumbnails"},
    config={"configurable": {
        "project_id": "proj_abc123",
        "video_ids": ["vid_1", "vid_2"],
    }}
)
```

**Which to use:**
- LangGraph + `create_react_agent`: use `ToolRuntime` with `context_schema` (cleaner, typed)
- Plain LangChain `AgentExecutor` or custom chains: use `RunnableConfig` with `configurable`
- New LangGraph `Runtime` API (0.6+): consider `Runtime[MyContext]` in node functions

### 5.3 Accessing Context in Node Functions (LangGraph)

For nodes (not tools), the pattern is:

```python
from langgraph.runtime import Runtime

@dataclass
class OrchestratorContext:
    project_id: str
    engagement_metrics: dict

def orchestrator_node(state: CreatorJoyState, runtime: Runtime[OrchestratorContext]):
    """Main orchestrator node — receives context directly."""
    metrics = runtime.context.engagement_metrics
    project_id = runtime.context.project_id
    
    # Build system prompt with pre-injected metrics
    system_prompt = build_orchestrator_prompt(metrics)
    ...
```

---

## 6. Streaming: Tool-Use Events to the User

### 6.1 What We Want

The user should see something like:
```
Using SearchSkill to find relevant video segments...
Using AnalysisSkill to analyze engagement patterns...
[Final answer streams token by token]
```

### 6.2 LangGraph `stream_mode="updates"` (Recommended for Our Case)

The simplest pattern for showing skill usage:

```python
async def chat_with_streaming(
    user_message: str,
    conversation_id: str,
    project_id: str,
    video_ids: list[str],
):
    """Stream orchestrator responses, surfacing skill usage events."""
    
    async for chunk in main_orchestrator.astream(
        {"messages": [HumanMessage(content=user_message)]},
        config={"configurable": {"thread_id": conversation_id}},
        context=OrchestratorContext(project_id=project_id, engagement_metrics={}),
        stream_mode="updates",
    ):
        # Each chunk is a dict: {node_name: state_update}
        for node_name, update in chunk.items():
            if node_name == "tools":
                # A tool was called — surface it to the user
                for message in update.get("messages", []):
                    if hasattr(message, "name"):
                        yield {"type": "skill_usage", "skill": message.name}
            
            elif node_name == "orchestrator":
                # Orchestrator is generating a response
                messages = update.get("messages", [])
                for msg in messages:
                    if hasattr(msg, "content") and msg.content:
                        yield {"type": "token", "content": msg.content}
```

### 6.3 `astream_events` v2 for Fine-Grained Events

For richer event handling (token-by-token streaming + tool events):

```python
async def stream_with_events(user_message: str, context: OrchestratorContext):
    """Stream using astream_events v2 for maximum granularity."""
    
    async for event in main_orchestrator.astream_events(
        {"messages": [HumanMessage(content=user_message)]},
        version="v2",
        config={"configurable": {"thread_id": "session_123"}},
    ):
        event_type = event["event"]
        
        # Tool is starting — show "Using [skill]..."
        if event_type == "on_tool_start":
            tool_name = event["name"]
            skill_display = tool_name.replace("_", " ").title()
            yield f"data: {json.dumps({'type': 'skill_start', 'skill': skill_display})}\n\n"
        
        # Tool finished — optionally show completion
        elif event_type == "on_tool_end":
            tool_name = event["name"]
            yield f"data: {json.dumps({'type': 'skill_end', 'skill': tool_name})}\n\n"
        
        # LLM is streaming tokens
        elif event_type == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield f"data: {json.dumps({'type': 'token', 'content': chunk.content})}\n\n"
        
        # Final answer complete
        elif event_type == "on_chain_end" and event["name"] == "main_orchestrator":
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
```

### 6.4 Custom Events from Inside Tools

For surfacing sub-agent progress within a tool call, use `get_stream_writer()`:

```python
from langgraph.config import get_stream_writer

@tool
def search_video_transcripts(query: str, runtime: ToolRuntime = None) -> list[dict]:
    """Search video transcripts."""
    stream_writer = get_stream_writer()
    
    # Emit progress event — visible to the streaming consumer
    stream_writer({"type": "progress", "message": f"Searching transcripts for: {query}"})
    
    results = qdrant_search(query, runtime.context.project_id)
    
    stream_writer({"type": "progress", "message": f"Found {len(results)} relevant segments"})
    
    return results
```

Consume custom events in your stream:

```python
async for event in agent.astream_events(..., version="v2"):
    if event["event"] == "on_custom_event":
        data = event["data"]
        yield f"data: {json.dumps(data)}\n\n"
```

### 6.5 FastAPI SSE Integration

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import json

app = FastAPI()

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    
    async def event_generator():
        async for event in stream_with_events(
            user_message=request.message,
            context=OrchestratorContext(
                project_id=request.project_id,
                engagement_metrics=await get_metrics(request.project_id),
            )
        ):
            yield event
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},  # disable nginx buffering
    )
```

**Important known issue:** As of early 2026, `astream_events` does not propagate events through nested LangGraph subgraphs by default. If you embed a compiled sub-agent as a subgraph node, you may not receive its internal events. Workaround: use `stream_mode="updates"` on the parent graph, or explicitly propagate events using custom event emission inside subgraph nodes.

---

## 7. Known Failure Modes and How to Avoid Them

This section is based on the MAST taxonomy (14 failure modes across 150+ execution traces, ICLR 2025), Anthropic's production experience, and the Bag-of-Agents research (DeepMind 2025).

### 7.1 The MAST Taxonomy: 14 Failure Modes

**Category 1: Specification and System Design Failures (41.77% of failures)**

| Failure Mode | Description | Our Mitigation |
|-------------|-------------|----------------|
| FM-1.1: Disobey task specification | Sub-agent ignores stated constraints | Use JSON schema for skill specs + explicit constraints in skill.md |
| FM-1.2: Disobey role specification | Agent oversteps defined responsibilities | Each skill.md must have explicit scope boundaries |
| FM-1.3: Step repetition | Redundant re-execution of completed steps | Track completed steps in SQLite; include in situational prompt |
| FM-1.4: Loss of conversation history | Context truncation | External persistence in SQLite; never rely on context window alone |
| FM-1.5: Unaware of termination conditions | Missing stop criteria | Explicit "stop when" conditions in skill.md; max_iterations in agent config |

**Category 2: Inter-Agent Misalignment (36.94% of failures)**

| Failure Mode | Description | Our Mitigation |
|-------------|-------------|----------------|
| FM-2.1: Conversation reset | Agent restarts dialogue inappropriately | Situational prompt explicitly states prior findings |
| FM-2.2: Fail to ask for clarification | Agent guesses ambiguous info | skill.md must specify: "if X is ambiguous, return what you found + the ambiguity" |
| FM-2.3: Task derailment | Sub-agent drifts from assigned task | Focused situational prompts; single-responsibility per skill |
| FM-2.4: Information withholding | Sub-agent doesn't report critical finding | skill.md must explicitly say: "always report all relevant findings even if surprising" |
| FM-2.5: Ignored other agent's input | Sub-agent discards prior findings | Structure situational prompt to make prior findings prominent |
| FM-2.6: Reasoning-action mismatch | Logic says X, action is Y | Enable model thinking/chain-of-thought in sub-agents |

**Category 3: Task Verification and Termination (21.30% of failures)**

| Failure Mode | Description | Our Mitigation |
|-------------|-------------|----------------|
| FM-3.1: Premature termination | Sub-agent stops before task complete | Explicit success criteria in skill.md |
| FM-3.2: No/incomplete verification | Missing output validation | Orchestrator should verify sub-agent output addresses the question |
| FM-3.3: Incorrect verification | Sub-agent wrongly validates its own output | Consider a lightweight critic pass for high-stakes responses |

### 7.2 The 17x Error Amplification Trap

DeepMind research ("Towards a Science of Scaling Agent Systems", 2025) found that **unstructured multi-agent networks amplify errors by 17.2x** vs. single agents. Centralized orchestration reduces this to 4.4x by functioning as a verification checkpoint.

The three characteristics of failing systems:
1. **Flat topology**: Agents connect peer-to-peer without hierarchy — our design avoids this
2. **Noisy chatter**: Agents validate each other's mistakes — our orchestrator synthesizes, not the sub-agents
3. **Open-loop execution**: No verification layer — the main agent implicitly verifies by synthesizing

Our design (single orchestrator → skill sub-agents → results back to orchestrator) is the correct topology. The orchestrator's synthesis step serves as the verification layer.

**Key quantitative insight:** Performance saturates around 4 sub-agents for most tasks; beyond this, additional agents contribute noise rather than value. For our use case, the common pattern will be 1-2 sub-agent calls per user message, rarely more than 3.

### 7.3 Context Window Collapse

When the orchestrator's context grows too large (from accumulated sub-agent findings), quality degrades non-linearly. Anthropic observed that their lead agent saved its plan to external memory when context approached the 200K token limit.

**Our mitigation:**
```python
MAX_CONTEXT_TOKENS = 12000  # conservative limit for orchestrator

def prepare_context_for_orchestrator(
    conversation_history: list[dict],
    accumulated_findings: list[str],
    current_engagement_metrics: dict,
) -> str:
    """Compress context to stay within budget."""
    
    # Compress findings if needed
    findings_text = "\n".join(accumulated_findings)
    if count_tokens(findings_text) > 3000:
        findings_text = summarize_findings(accumulated_findings)
    
    # Trim conversation history to last N turns
    trimmed_history = conversation_history[-6:]  # last 3 exchanges
    
    return {
        "history": trimmed_history,
        "findings": findings_text,
        "metrics": current_engagement_metrics,
    }
```

### 7.4 Sub-Agent Routing Loops

When the orchestrator keeps calling the same skill without progress.

**Mitigation:**
```python
@dataclass
class OrchestratorState:
    skill_call_count: dict[str, int] = field(default_factory=dict)
    MAX_SKILL_CALLS = 3  # per skill per conversation turn

def validate_skill_call(skill_name: str, state: OrchestratorState) -> bool:
    count = state.skill_call_count.get(skill_name, 0)
    if count >= OrchestratorState.MAX_SKILL_CALLS:
        return False  # prevent loop
    state.skill_call_count[skill_name] = count + 1
    return True
```

### 7.5 Error Propagation: Silent Failures

When a tool fails (empty Qdrant results, DB error) and the sub-agent silently returns "no results found" without signaling the error type, the orchestrator can't correct course.

**Mitigation: structured tool returns:**

```python
from pydantic import BaseModel
from typing import Literal

class ToolResult(BaseModel):
    status: Literal["success", "empty", "error"]
    data: list | dict | None
    message: str  # human-readable, ALWAYS populated

@tool
def search_video_transcripts(query: str, runtime: ToolRuntime = None) -> ToolResult:
    """Search video transcripts."""
    try:
        results = qdrant_search(query, runtime.context.project_id)
        if not results:
            return ToolResult(status="empty", data=[], message="No transcript segments matched this query.")
        return ToolResult(status="success", data=results, message=f"Found {len(results)} segments.")
    except Exception as e:
        return ToolResult(status="error", data=None, message=f"Search failed: {str(e)}")
```

Approximately 60% of hallucinated responses in agentic RAG systems originate from unhandled execution errors that propagate silently.

### 7.6 Infinite Retrieval Loops

Sub-agents can enter loops of repeated retrieval calls without converging. Relevant for our SearchSkill.

**Mitigation:**
- Set `recursion_limit` in LangGraph agent config: `create_react_agent(..., debug=False)` compiles with default recursion limit of 25
- Override per-invocation: `agent.ainvoke(..., config={"recursion_limit": 10})`
- In skill.md: "If you have called search twice without finding what you need, report that the information is not available rather than searching again."

### 7.7 Source Quality Bias

Anthropic's production system found agents consistently chose SEO-optimized content over authoritative sources. For our RAG system, the equivalent is: the model preferring high-similarity but shallow transcript chunks over lower-similarity but contextually richer ones.

**Mitigation:** Implement a reranker after Qdrant retrieval that scores for relevance AND informativeness. Pass reranked results only.

### 7.8 Specification Drift: Vague Skill.md Files

The most common root cause of failures is vague role definitions. Agents cannot "read between the lines" during execution — every ambiguity is a branch point where they pick suboptimally.

**Mitigation — skill.md must include:**
```markdown
# SearchSkill

## Role
You search video transcripts and metadata to find relevant information.

## Scope (what you DO)
- Semantic search over transcript segments
- Keyword search over video titles, descriptions
- Retrieving specific clips by timestamp

## Out of Scope (what you DO NOT do)
- Analysis or interpretation of what you find
- Recommendations or advice
- Anything requiring data not in the transcripts/metadata

## Success Criteria
Your task is complete when you have retrieved the most relevant segments.
Do not continue searching if you have retrieved 5+ relevant results.

## If Search Fails
If no relevant results are found after 2 searches with different queries,
report: "No relevant content found for: [query]" and stop.
```

---

## 8. Specific Recommendations for Our Architecture

### 8.1 Orchestrator System Prompt Structure

The main Gemini agent's system prompt should be organized as:

```
SECTION 1: Role and Capability Overview
- What CreatorJoy does
- The kinds of questions it answers
- The creator's context (injected at runtime)

SECTION 2: Engagement Metrics (pre-injected per session)
- Current ER, views, likes, CTR, retention
- Recent trend indicators
- Key benchmarks for this creator's niche

SECTION 3: Available Skills
For each skill:
  - Name
  - What it does (1 sentence)
  - When to use it
  - What it returns

SECTION 4: Orchestration Strategy
- How to decompose complex questions
- When to call multiple skills sequentially
- How to synthesize findings into a response
- What NOT to prescribe in situational prompts
```

### 8.2 Skill Registry Implementation

```python
import os
from pathlib import Path
from dataclasses import dataclass, field

SKILLS_DIR = Path(__file__).parent / "skills"

@dataclass
class Skill:
    name: str
    description: str       # for orchestrator system prompt (1-2 sentences)
    when_to_use: str       # for orchestrator system prompt
    prompt_path: Path
    tools: list
    _prompt_cache: str = field(default=None, repr=False)
    
    @property
    def prompt(self) -> str:
        if not self._prompt_cache:
            self._prompt_cache = self.prompt_path.read_text()
        return self._prompt_cache

# Define skills
SKILLS = {
    "search": Skill(
        name="search",
        description="Searches video transcripts and metadata using semantic and keyword search.",
        when_to_use="When you need to find specific moments, topics, or quotes from the creator's videos.",
        prompt_path=SKILLS_DIR / "search_skill.md",
        tools=[search_video_transcripts, search_video_metadata],
    ),
    "analysis": Skill(
        name="analysis",
        description="Analyzes engagement metrics, trends, and patterns across videos.",
        when_to_use="When you need to understand why certain videos performed well or poorly.",
        prompt_path=SKILLS_DIR / "analysis_skill.md",
        tools=[get_engagement_metrics, compare_videos, get_trend_data],
    ),
    "chat": Skill(
        name="chat",
        description="Handles general conversation, explanations, and synthesis.",
        when_to_use="For direct answers from retrieved data or general YouTube strategy questions.",
        prompt_path=SKILLS_DIR / "chat_skill.md",
        tools=[],  # chat skill may need no tools
    ),
}

def build_skills_section() -> str:
    """Generate the skills section for the orchestrator system prompt."""
    lines = ["## Available Skills\n"]
    for skill in SKILLS.values():
        lines.append(f"### {skill.name}")
        lines.append(f"**What it does:** {skill.description}")
        lines.append(f"**Use when:** {skill.when_to_use}\n")
    return "\n".join(lines)
```

### 8.3 Complete Main Agent Tool Implementation

```python
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from langchain_google_genai import ChatGoogleGenerativeAI

def make_use_skill_tool(project_id: str, video_ids: list[str]):
    """
    Factory: creates the use_sub_agent_with_skill tool with project context bound.
    This is called once per session; project_id and video_ids never go through the LLM.
    """
    
    @tool
    async def use_sub_agent_with_skill(skill_name: str, situational_prompt: str) -> str:
        """Invoke a specialized skill to handle a specific sub-task.
        
        Args:
            skill_name: The name of the skill to use (search, analysis, chat)
            situational_prompt: Detailed briefing for the skill agent including: 
                                 overall goal, prior findings, current task, why this skill
        """
        if skill_name not in SKILLS:
            return f"Error: unknown skill '{skill_name}'. Available: {list(SKILLS.keys())}"
        
        skill = SKILLS[skill_name]
        
        # Create agent with skill.md as system prompt
        agent = create_react_agent(
            model=ChatGoogleGenerativeAI(model="gemini-2.0-flash"),
            tools=skill.tools,
            context_schema=SubAgentContext,
            prompt=lambda state, runtime: [SystemMessage(content=runtime.context.skill_prompt)],
        )
        
        try:
            result = await agent.ainvoke(
                {"messages": [HumanMessage(content=situational_prompt)]},
                context=SubAgentContext(
                    project_id=project_id,         # injected, LLM never sees
                    video_ids=video_ids,            # injected, LLM never sees
                    skill_prompt=skill.prompt,
                ),
                config={"recursion_limit": 10},
            )
            return result["messages"][-1].content
        except Exception as e:
            return f"Skill '{skill_name}' encountered an error: {str(e)}"
    
    return use_sub_agent_with_skill
```

### 8.4 Session Initialization Pattern

```python
async def create_orchestrator_for_session(
    project_id: str,
    video_ids: list[str],
    engagement_metrics: dict,
) -> CompiledStateGraph:
    """
    Create the main orchestrator agent for a session.
    Engagement metrics and skill catalog are baked into the system prompt.
    """
    
    # Build system prompt with pre-injected metrics
    system_prompt = f"""You are CreatorJoy, an AI assistant for YouTube creators.

## Creator Context
Project ID: {project_id}
Videos in scope: {len(video_ids)} videos

## Current Engagement Metrics
{format_metrics(engagement_metrics)}

{build_skills_section()}

## How to Use Skills
When a user question requires data from the creator's videos or analytics,
use use_sub_agent_with_skill with a detailed situational prompt.

A good situational prompt:
- States the overall goal (what the user wants to know)
- Summarizes what has already been found (if anything)
- Specifies exactly what to find NOW
- Does NOT tell the skill how to format its answer

A bad situational prompt only says: "find information about thumbnails"
A good situational prompt says: "Goal: understand why March 2026 videos underperformed.
Prior findings: engagement data shows CTR dropped 40% in March.
Current task: search transcripts and titles of March 2026 videos for 
changes in thumbnail style, topic focus, or posting patterns."
"""
    
    # Bind project context to the tool
    skill_tool = make_use_skill_tool(project_id, video_ids)
    
    orchestrator = create_react_agent(
        model=ChatGoogleGenerativeAI(model="gemini-2.0-pro"),
        tools=[skill_tool],
        prompt=system_prompt,
    )
    
    return orchestrator
```

### 8.5 What to Build Next (Prioritized)

**Phase 1 — Get the core loop working:**
1. Implement `SubAgentContext` dataclass and `ToolRuntime` injection in all tools
2. Implement `use_sub_agent_with_skill` tool factory
3. Wire session initialization with metrics pre-injection
4. Test with a simple two-skill chain (search → analysis)

**Phase 2 — Add streaming:**
1. Add `get_stream_writer()` calls to tools for progress events
2. Implement SSE endpoint with `astream_events` v2
3. Build frontend event handler for skill_start / skill_end / token events

**Phase 3 — Harden against failure modes:**
1. Add structured `ToolResult` returns from all tools
2. Add per-skill call counting and loop prevention
3. Add context compression for long conversations
4. Add explicit success criteria to all skill.md files

**Phase 4 — Optimize:**
1. Cache compiled sub-agent graphs with `lru_cache`
2. Enable parallel sub-agent invocations where findings are independent
3. Add a lightweight critic pass for high-stakes responses

---

## 9. Sources

### LangGraph / LangChain Documentation
- [LangGraph Multi-Agent Supervisor Package](https://reference.langchain.com/python/langgraph-supervisor)
- [LangGraph Supervisor GitHub Repository](https://github.com/langchain-ai/langgraph-supervisor-py)
- [create_react_agent API Reference](https://reference.langchain.com/python/langgraph.prebuilt/chat_agent_executor/create_react_agent)
- [ToolRuntime API Reference](https://reference.langchain.com/python/langgraph.prebuilt/tool_node/ToolRuntime)
- [LangGraph Runtime Class Reference](https://reference.langchain.com/python/langgraph/runtime/Runtime)
- [LangChain RunnableConfig Documentation](https://python.langchain.com/api_reference/core/runnables/langchain_core.runnables.config.RunnableConfig.html)
- [LangChain How to Access RunnableConfig from a Tool](https://python.langchain.com/docs/how_to/tool_configure/)
- [astream_events API Reference](https://reference.langchain.com/python/langchain-core/runnables/base/Runnable/astream_events)
- [LangChain Streaming Documentation](https://docs.langchain.com/oss/python/langchain/streaming)
- [LangGraph context.configurable API Discussion](https://github.com/langchain-ai/langgraph/issues/5023)

### Research Papers
- [Why Do Multi-Agent LLM Systems Fail? (MAST Taxonomy, ICLR 2025)](https://arxiv.org/html/2503.13657v1)
- [Multi-Agent LLM Orchestration for Incident Response (arXiv 2025)](https://arxiv.org/abs/2511.15755)
- [Agentic Retrieval-Augmented Generation Survey (arXiv 2025)](https://arxiv.org/html/2501.09136v4)

### Architecture Guides and Production Reports
- [Anthropic: How We Built Our Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Anthropic: Multi-Agent Coordination Patterns](https://claude.com/blog/multi-agent-coordination-patterns)
- [Towards Data Science: Why Your Multi-Agent System is Failing (17x Error Trap)](https://towardsdatascience.com/why-your-multi-agent-system-is-failing-escaping-the-17x-error-trap-of-the-bag-of-agents/)
- [Augment Code: Why Multi-Agent LLM Systems Fail and How to Fix Them (2026)](https://www.augmentcode.com/guides/why-multi-agent-llm-systems-fail-and-how-to-fix-them)
- [Vellum: Multi-Agent Systems with Context Engineering](https://www.vellum.ai/blog/multi-agent-systems-building-with-context-engineering)
- [DEV Community: Multi-Agent Orchestration in LangGraph: Supervisor vs Swarm](https://dev.to/focused_dot_io/multi-agent-orchestration-in-langgraph-supervisor-vs-swarm-tradeoffs-and-architecture-1b7e)
- [Latenode: LangGraph Multi-Agent Orchestration Complete Guide (2025)](https://latenode.com/blog/ai-frameworks-technical-infrastructure/langgraph-multi-agent-orchestration/langgraph-multi-agent-orchestration-complete-framework-guide-architecture-analysis-2025)
- [Next-Generation Agentic RAG with LangGraph (2026 Edition)](https://medium.com/@vinodkrane/next-generation-agentic-rag-with-langgraph-2026-edition-d1c4c068d2b8)
- [InfoQ: Building Hierarchical Agentic RAG Systems](https://www.infoq.com/articles/building-hierarchical-agentic-rag-systems/)
- [Orq.ai: Why Do Multi-Agent LLM Systems Fail?](https://orq.ai/blog/why-do-multi-agent-llm-systems-fail)
- [Orq.ai: LLM Orchestration Best Practices 2026](https://orq.ai/blog/llm-orchestration)
- [Azure Architecture: AI Agent Design Patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)
