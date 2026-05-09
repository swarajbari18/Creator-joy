# Gemini Tool Calling: Developer Reference

**Audience:** Engineers implementing the LangChain multi-agent tool layer for Creator-Joy  
**Last updated:** May 2026  
**Stack:** Python · LangChain `langchain-google-genai` · `ChatGoogleGenerativeAI` · Gemini 2.5 Flash / Pro

---

## Table of Contents

1. [How Gemini Tool Calling Works (Mechanics)](#1-how-gemini-tool-calling-works-mechanics)
2. [Gemini vs OpenAI vs Anthropic — Key Differences](#2-gemini-vs-openai-vs-anthropic--key-differences)
3. [Type Annotation Compatibility Matrix](#3-type-annotation-compatibility-matrix)
4. [LangChain-Specific Gaps and Bugs](#4-langchain-specific-gaps-and-bugs)
5. [Streaming + Tool Use — How to Do It Correctly](#5-streaming--tool-use--how-to-do-it-correctly)
6. [Correct Tool Definition Patterns with Code Examples](#6-correct-tool-definition-patterns-with-code-examples)
7. [Model Recommendations for Agentic Workloads](#7-model-recommendations-for-agentic-workloads)
8. [Known Workarounds Cheatsheet](#8-known-workarounds-cheatsheet)
9. [Sources](#9-sources)

---

## 1. How Gemini Tool Calling Works (Mechanics)

### The Basic Loop

Gemini tool calling is a 4-step request-response cycle. The model never executes functions itself — your application does:

```
1. You send: user prompt + function declarations (inside GenerateContentConfig.tools)
2. Model returns: a functionCall part with { name, args, id }
3. You execute: run the function with args
4. You send: functionResponse part with { name, response, id } back to model
5. Model returns: final natural-language answer incorporating the result
```

### Function Declarations Format

Unlike OpenAI (which uses JSON Schema inline), Gemini uses Protocol Buffer types via `types.Schema` and `types.Type` enums internally. The Python SDK and LangChain abstract this for you, but the underlying format matters when things go wrong:

```python
# Raw google-genai SDK (for debugging / manual control)
from google.genai import types

get_weather_decl = types.FunctionDeclaration(
    name="get_weather",
    description="Get current weather for a location",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "location": types.Schema(
                type=types.Type.STRING,
                description="City name, e.g. 'Berlin'"
            )
        },
        required=["location"]
    )
)

config = types.GenerateContentConfig(
    tools=[types.Tool(function_declarations=[get_weather_decl])]
)
```

### Parallel Function Calling

Gemini supports calling multiple functions in a **single turn** when the model determines they are independent. The model returns multiple `functionCall` objects in one response. Key behavior:

- Results do **not** need to be returned in the same order as calls
- The API maps each result to its originating call via the `id` field (critical in Gemini 2.5+)
- For Python LangChain users: the `id` is surfaced in `AIMessage.tool_calls[n].id`

### Function ID Handling (Gemini 2.5 + Gemini 3)

Starting with Gemini 2.5, every `functionCall` includes a unique `id`. In Gemini 3 this is **mandatory** — the API will reject multi-turn tool responses that lack the matching `id`. LangChain's `ToolMessage` carries `tool_call_id` which maps to this. Always preserve the original `AIMessage` object and pass it back unmodified rather than reconstructing messages manually.

### Thought Signatures (Thinking Models — Gemini 2.5 Flash with thinking enabled, Gemini 3)

When thinking is enabled, the model embeds an encrypted `thought_signature` in every `functionCall` part. The rules are strict:

- The signature **must** be echoed back in the corresponding `functionResponse`
- Never merge a `Part` containing a signature with one that does not
- Never reconstruct `AIMessage` from scratch after receiving tool calls — pass the whole object back

Failure to do this produces: `400 Function call is missing a thought_signature`.

### Tool Config / Calling Modes

Control how aggressively Gemini calls tools via `tool_config`:

| Mode | Behavior |
|------|----------|
| `AUTO` (default) | Model decides whether to call a tool or respond in natural language |
| `ANY` | Forces the model to always call a tool (one of the declared ones) |
| `NONE` | Prohibits all tool calls |
| `allowed_function_names` | Restricts which subset of tools can be chosen |

In LangChain, `bind_tools(tools, tool_choice="any")` maps to `ANY` mode.

---

## 2. Gemini vs OpenAI vs Anthropic — Key Differences

| Aspect | Gemini | OpenAI | Anthropic Claude |
|--------|--------|--------|-----------------|
| **Role for tool results** | `user` (with `function` role in parts) | `tool` role | `user` role with `tool_result` type |
| **Conversation roles** | `user` → `model` → `user` (function response) | `user` → `assistant` → `tool` | `user` → `assistant` → `user` |
| **Function call ID** | Required in 2.5+, mandatory in Gemini 3 | Explicit `tool_call_id` must match | Explicit `tool_use_id` must match |
| **Arguments type** | Proto object — use `dict(call.args)` to access | JSON string — must parse | Pre-parsed dict |
| **Call detection** | Check `function_call` in `parts[]` | Check `message.tool_calls` | Check `stop_reason == "tool_use"` |
| **Type system** | Subset of OpenAPI schema (no `anyOf` alongside other fields) | Full JSON Schema | Full JSON Schema |
| **Parallel calls** | Supported; all in one response chunk (Flash) or split across chunks (Pro) | Supported; can disable with `parallel_tool_calls=false` | Supported |
| **Disable parallel calls** | No native API flag; requires application-level loop control | `parallel_tool_calls: false` | No flag |
| **Native grounding tools** | Google Search, Code Execution, Maps, URL Context | Web search (plugin) | Web search (tool) |
| **Thought signatures** | Required for thinking models | Not applicable | Not applicable |
| **Re-declare tools per request** | Yes — no persistent function registry | Yes | Yes |

### Critical Role Naming Note

OpenAI conversation flow: `user` → `assistant` → `tool`  
Gemini conversation flow: `user` → `model` → `user` (function response is in a `user`-role message)

This causes silent misrouting if you copy OpenAI-style history management code to a Gemini integration.

### Occasionally Empty Arguments

Gemini occasionally generates function calls with **empty arguments** when a parameter is ambiguous. OpenAI does too, but Gemini's frequency is reported higher. Always validate `args` before executing:

```python
if not call.args or len(call.args) == 0:
    # Handle gracefully — ask model for clarification or use defaults
```

---

## 3. Type Annotation Compatibility Matrix

The Python SDK's automatic schema extraction supports a **strict subset** of Python types. Using unsupported types causes either a silent drop (parameter missing from the schema) or a 400 error from the API.

### Supported Types (Safe to Use)

| Python Type | Gemini Schema Type | Notes |
|-------------|-------------------|-------|
| `str` | `STRING` | Always works |
| `int` | `INTEGER` | Always works |
| `float` | `NUMBER` | Always works |
| `bool` | `BOOLEAN` | Always works |
| `list[str]` | `ARRAY` of `STRING` | Works |
| `list[int]` | `ARRAY` of `INTEGER` | Works |
| `list[float]` | `ARRAY` of `NUMBER` | Works |
| `Optional[str]` | `STRING` (nullable) | Works — `Optional[X]` is the one allowed Union form |
| `pydantic.BaseModel` subclass | `OBJECT` with properties | Works if all fields use allowed types |
| `dict` (no type params) | Avoid — see below | Risky |

### Problematic / Unsupported Types

| Python Type | Problem | Workaround |
|-------------|---------|------------|
| `Union[int, float]` | Generates `anyOf` which Gemini rejects if other fields also present | Use `float` (broadest single type) |
| `Optional[date \| datetime]` | Union of non-primitives not included in schema at all | Use `str` with ISO 8601 format description |
| `dict[str, int]` | Typed dicts lack robust support | Use `pydantic.BaseModel` instead |
| `dict` / `Dict[str, Any]` | API rejects "object with unknown properties" | Define an explicit `BaseModel` with named fields |
| Deeply nested schemas | API may reject very large or deeply nested schemas in `ANY` mode | Flatten schema; use max 2–3 nesting levels |
| `additionalProperties: false` | SDK client-side validator rejects it despite API supporting it since Nov 2025 | Use `response_json_schema` bypass or update to latest SDK |
| `.nullish()` (Zod / JS) | Causes 400 in ChatVertexAI (JS) | Use `.optional()` instead |
| `anyOf` alongside other fields | API rejects: "When using any_of, it must be the only field set" | Avoid mixed anyOf; use single concrete type |

### The `anyOf` Rule (Critical)

Gemini's API is strict: **if `anyOf` is present in a schema node, it must be the only key**. LangChain's schema converter (before PR #1330 fix) generated `anyOf` with additional sibling properties. This produces:

```
Unable to submit request because `tool_name` functionDeclaration `parameters.field` 
schema specified other fields alongside any_of. When using any_of, it must be the only field set.
```

**Workaround:** Use single concrete types. `Union[int, float]` → `float`. `Union[str, int]` → `str`.

### Pydantic Model Best Practice

Use Pydantic models for tool arguments with complex inputs. All fields must use the supported primitive types:

```python
from pydantic import BaseModel, Field
from langchain_core.tools import tool

class SearchArgs(BaseModel):
    query: str = Field(description="The search query string")
    max_results: int = Field(default=5, description="Maximum number of results to return")
    language: str = Field(default="en", description="ISO 639-1 language code")

@tool(args_schema=SearchArgs)
def search_documents(query: str, max_results: int = 5, language: str = "en") -> str:
    """Search for documents in the knowledge base."""
    # implementation
    return "results"
```

---

## 4. LangChain-Specific Gaps and Bugs

### 4.1 Only First Tool Accessible (Fixed in ~v1.0.8)

**Issue:** `langchain-google-genai` v1.0.7 — when multiple tools are bound, Gemini only sees and uses the first one.  
**Symptom:** Model responds "I don't have access to [tool 2 or 3]" even when they are bound.  
**GitHub:** [langchain-ai/langchain-google #369](https://github.com/langchain-ai/langchain-google/issues/369)  
**Fix:** Addressed in PR #387. Update to `langchain-google-genai >= 1.0.8`.

### 4.2 Union Types Break Schema Generation (Partially Fixed)

**Issue:** `Union[X, Y]` type hints (except `Optional[T]`) cause API rejection.  
**Error:** `Unable to submit request because schema specified other fields alongside any_of`  
**GitHub:** [langchain-ai/langchain-google #1216](https://github.com/langchain-ai/langchain-google/issues/1216), [#463](https://github.com/langchain-ai/langchain-google/issues/463)  
**Fix:** PR #1330 partially addressed this. Workaround: use single concrete types. `Union[int, float]` → `float`.

### 4.3 Tool Name Validation Failure

**Issue:** Tool names with spaces, special chars, or >64 chars are rejected by Gemini API.  
**Error:** `Invalid function name. Must start with a letter or an underscore...`  
**GitHub:** [langchain-ai/langchain-google #1332](https://github.com/langchain-ai/langchain-google/issues/1332)  
**Gemini name rules:** Must match `[a-zA-Z_][a-zA-Z0-9_.:−]*`, max 64 characters.  
**Workaround:**
```python
for tool in tools:
    tool.name = tool.name.strip().replace(' ', '_').replace('-', '_').lower()[:64]
llm_with_tools = llm.bind_tools(tools)
```

### 4.4 `ToolMessage.name` Not Set in Legacy Agent

**Issue:** When using LCEL legacy agents, `ToolMessage.name` is empty; Gemini's API expects the function name in the response and returns a 400 error.  
**Error:** `400` / tool call ID mismatch  
**GitHub:** [langchain-ai/langchain-google #711](https://github.com/langchain-ai/langchain-google/issues/711), [langchain-ai/langchain #29418](https://github.com/langchain-ai/langchain/issues/29418)  
**Fix:** Use `create_react_agent` from `langgraph.prebuilt` instead of the legacy LCEL agent. If stuck on legacy: manually set `tool_message.name = tool_call["name"]` before appending to message history.

### 4.5 Cannot Mix Native Gemini Tools with Custom LangChain Tools

**Issue:** Binding both built-in Gemini tools (e.g., `google_search`, `code_execution`) and custom function tools in a single `.bind_tools()` call fails.  
**GitHub:** [langchain-ai/langchainjs #10819](https://github.com/langchain-ai/langchainjs/issues/10819)  
**Workaround:** Maintain separate model instances — one for web search/grounding, one for custom tools. Route at the application layer.

### 4.6 `with_structured_output()` Conflicts with Tool Binding

**Issue:** When using `.with_structured_output()` together with `.bind()` for tools like `google_search`, the bound tool is ignored.  
**GitHub:** [langchain-ai/langchain-google #1289](https://github.com/langchain-ai/langchain-google/issues/1289)  
**Workaround:** For combined structured extraction + Google Search grounding, use `.bind()` with `response_mime_type="application/json"` and `response_schema` instead of `with_structured_output()`. For pure structured output, `method="json_schema"` (the default) is more reliable than `method="function_calling"`.

### 4.7 Context Caching Incompatibility with Tool Binding

**Issue:** Gemini API forbids passing `tools`, `system_instruction`, or `tool_config` in a `GenerateContent` request when using cached content.  
**Error:** `CachedContent can not be used with GenerateContent request setting system_instruction, tools or tool_config`  
**GitHub:** [langchain-ai/langchain-google #1528](https://github.com/langchain-ai/langchain-google/issues/1528)  
**Workaround:** Pre-define tools within `CachedContentConfig` at cache creation time; do not use `bind_tools()` on a model configured with `cached_content`.

### 4.8 Gemini 2.5 Flash Empty Response in LangGraph

**Issue:** Gemini 2.5 Flash (especially preview snapshots) generates empty responses during tool invocation cycles in LangGraph, causing `contents.parts must not be empty` errors on the next API call.  
**Error:** `InvalidArgument: 400 * GenerateContentRequest.contents[2].parts: contents.parts must not be empty`  
**GitHub:** [langchain-ai/langgraph #4780](https://github.com/langchain-ai/langgraph/issues/4780)  
**Workaround:** Use the stable GA release of Gemini 2.5 Flash (`gemini-2.5-flash` not `gemini-2.5-flash-preview-*`). Filter out empty `AIMessage` objects before appending to the graph state.

### 4.9 Gemini 3 `thought_signature` Missing Error

**Issue:** With Gemini 3 models and `include_thoughts=True`, tool calling fails because `create_react_agent` doesn't preserve the `thought_signature` in the reconstructed message history.  
**Error:** `InvalidArgument: 400 Function call is missing a thought_signature`  
**GitHub:** [langchain-ai/langchain-google #1364](https://github.com/langchain-ai/langchain-google/issues/1364)  
**Workaround:** Pass the entire original `AIMessage` back in history. Do not reconstruct `AIMessage` from `content` fields alone. When using `create_react_agent`, avoid thinking models until the LangGraph integration is patched (issue open as of late 2025).  
**Note:** This affects Gemini 3+ and Gemini 2.5 Flash with `thinking_budget > 0`. For our system using Gemini 2.5 Flash with thinking off (`thinking_budget=0`), this is avoided.

### 4.10 `SlackToolkit` and Other Community Tools Schema Incompatibility

**Issue:** Community toolkit tools that lack an explicit `args_schema` class fail Gemini's schema validation.  
**Error:** `400 * GenerateContentRequest.tools[0].function_declarations[0].parameters.properties[args].items: missing field`  
**GitHub:** [langchain-ai/langchain-google #1079](https://github.com/langchain-ai/langchain-google/issues/1079)  
**Workaround:** Add a minimal Pydantic `BaseModel` as `args_schema` to any community tool that lacks one:
```python
from pydantic import BaseModel

class MyToolSchema(BaseModel):
    pass  # or add actual fields

my_tool.args_schema = MyToolSchema
```

### 4.11 Streaming Callback `on_llm_new_token` Not Firing

**Issue:** The `on_llm_new_token` callback does not trigger with `ChatGoogleGenerativeAI` v2.1.10+ when streaming.  
**Warning:** Passing `streaming=True` generates: `Unexpected argument 'streaming' provided to ChatGoogleGenerativeAI`  
**GitHub:** [langchain-ai/langchain-google #1150](https://github.com/langchain-ai/langchain-google/issues/1150)  
**Workaround:** Use `model_kwargs={"streaming": True}` or simply iterate `.stream()` directly without relying on callback hooks.

### 4.12 `UNEXPECTED_TOOL_CALL` Finish Reason

**Issue:** `gemini-2.5-flash-lite` (and sometimes regular 2.5 Flash) stops with `finish_reason: UNEXPECTED_TOOL_CALL` even when no tools were passed.  
**GitHub:** [langchain-ai/langchainjs #8589](https://github.com/langchain-ai/langchainjs/issues/8589)  
**Workaround:** Always check `finish_reason` in the response. If `UNEXPECTED_TOOL_CALL`, re-invoke without tools or with `tool_config=NONE`.

---

## 5. Streaming + Tool Use — How to Do It Correctly

### The Core Problem

When tools are bound to `ChatGoogleGenerativeAI`, streaming **breaks** — the model returns a single consolidated `AIMessageChunk` instead of token-by-token chunks. This is a fundamental behavior difference in how Gemini handles tool-calling responses.

**GitHub:** [langchain-ai/langgraph #4877](https://github.com/langchain-ai/langgraph/issues/4877) — opened May 2025, still a known limitation.

### What Actually Happens

```
Without tools: stream delivers N token chunks → works correctly
With tools bound: stream delivers 1 large AIMessageChunk → effectively not streaming
```

### Parallel Tool Calls in Streaming Mode (Flash vs Pro)

There is an additional bug specific to Gemini 2.5 Flash in streaming mode with parallel tool calls:

- **Gemini 2.5 Flash** groups all parallel `functionCall` objects in a single response chunk. LangChain's streaming parser only processes the first one, silently dropping the rest.
- **Gemini 2.5 Pro** distributes each tool call across separate chunks — sequential parsing works.

**GitHub:** [langchain-ai/langchainjs #8454](https://github.com/langchain-ai/langchainjs/issues/8454)

### Recommended Streaming Strategy

**Option A — Use `.invoke()` for tool-calling steps, stream only final response (Recommended)**

This is the cleanest pattern for a multi-agent system:

```python
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, ToolMessage

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
llm_with_tools = llm.bind_tools(tools)

# Step 1: invoke (not stream) to get tool calls
ai_msg = llm_with_tools.invoke(messages)

# Step 2: execute tools
tool_results = execute_tools(ai_msg.tool_calls)
tool_messages = [
    ToolMessage(content=result, tool_call_id=call["id"], name=call["name"])
    for call, result in zip(ai_msg.tool_calls, tool_results)
]

# Step 3: stream the final answer (no tools bound here)
for chunk in llm.stream(messages + [ai_msg] + tool_messages):
    print(chunk.content, end="", flush=True)
```

**Option B — Disable streaming at the model level when tools are active**

LangChain supports a `disable_streaming` parameter on `ChatGoogleGenerativeAI`. Setting it to `"tool_calling"` makes the model use `.invoke()` internally whenever the model is invoked with tools, while still streaming for non-tool calls:

```python
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    disable_streaming="tool_calling"  # disables streaming only during tool-calling steps
)
```

**Option C — Use LangGraph's `.astream_events()` with `stream_mode="messages"`**

In LangGraph, even though the underlying LLM call returns a single chunk, LangGraph's event system can provide per-node streaming. For user-facing streaming of the final answer, route to a dedicated "final answer" node that uses `llm.astream()` without tools:

```python
# LangGraph pattern: separate tool-calling node from streaming output node
async def call_model_node(state):
    # Uses invoke — no streaming, returns tool calls
    return {"messages": [llm_with_tools.invoke(state["messages"])]}

async def stream_final_answer_node(state):
    # Uses stream — no tools, delivers token stream
    async for chunk in llm.astream(state["messages"]):
        yield chunk
```

### Structured Output Streaming

When streaming structured output (without tools), merge chunks as dicts, not strings:

```python
full = None
for chunk in llm.with_structured_output(MyModel).stream(prompt):
    if full is None:
        full = chunk
    else:
        full = full.update(chunk)  # dict merge, NOT +=
```

---

## 6. Correct Tool Definition Patterns with Code Examples

### Pattern 1 — Simple Function with `@tool` Decorator (Preferred)

The simplest and most Gemini-compatible approach. Use primitive types only.

```python
from langchain_core.tools import tool

@tool
def get_channel_metrics(channel_id: str, metric_type: str) -> str:
    """
    Retrieve performance metrics for a YouTube channel.

    Args:
        channel_id: The YouTube channel ID (e.g., 'UCxxxxxx')
        metric_type: Type of metric to retrieve. One of: 'views', 'subscribers', 'engagement'

    Returns:
        JSON string with metric data
    """
    # implementation
    return '{"views": 1000000}'
```

**Key rule:** The docstring's first paragraph becomes the function description. The `Args:` section provides parameter descriptions. Gemini uses these — write them clearly.

### Pattern 2 — Pydantic `args_schema` for Complex Inputs

Use this when you have multiple parameters, defaults, or need validation:

```python
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from typing import Optional

class QdrantSearchArgs(BaseModel):
    """Input schema for Qdrant semantic search."""
    query: str = Field(description="The semantic search query text")
    collection: str = Field(description="Qdrant collection name to search in")
    top_k: int = Field(default=5, description="Number of results to return (1-20)")
    score_threshold: float = Field(
        default=0.7,
        description="Minimum similarity score threshold (0.0 to 1.0)"
    )
    # Note: avoid Optional[complex_type] — use Optional[str] only
    filter_tag: Optional[str] = Field(
        default=None,
        description="If provided, filter results to only this tag"
    )

@tool(args_schema=QdrantSearchArgs)
def search_qdrant(
    query: str,
    collection: str,
    top_k: int = 5,
    score_threshold: float = 0.7,
    filter_tag: Optional[str] = None
) -> str:
    """Search the Qdrant vector database for semantically similar documents."""
    # implementation
    return "results"
```

### Pattern 3 — Tool as a Class (StructuredTool)

For tools that need state (e.g., a Qdrant client instance):

```python
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field

class AnalysisArgs(BaseModel):
    video_id: str = Field(description="YouTube video ID")
    analysis_type: str = Field(description="Type: 'sentiment', 'topics', or 'style'")

def run_video_analysis(video_id: str, analysis_type: str) -> str:
    """Run analysis on a video. Returns JSON analysis results."""
    # implementation using injected client
    return "{}"

analysis_tool = StructuredTool.from_function(
    func=run_video_analysis,
    name="run_video_analysis",          # Must be alphanumeric + underscore only
    description="Analyze a YouTube video for sentiment, topics, or content style.",
    args_schema=AnalysisArgs
)
```

### Pattern 4 — Binding Tools to `ChatGoogleGenerativeAI`

```python
from langchain_google_genai import ChatGoogleGenerativeAI

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=1.0,          # Keep at 1.0 for Gemini 2.5+ (avoid loops)
    thinking_budget=0,        # Set to 0 to disable thinking (avoids thought_signature issues)
    max_output_tokens=8192,
)

# Bind tools
tools = [search_qdrant, run_video_analysis, get_channel_metrics]
llm_with_tools = llm.bind_tools(tools)

# Optional: force at least one tool call
llm_must_use_tool = llm.bind_tools(tools, tool_choice="any")

# Optional: force a specific tool
llm_must_search = llm.bind_tools(tools, tool_choice="search_qdrant")
```

### Pattern 5 — Disabling Automatic Function Calling (when you want manual control)

The google-genai SDK has an "automatic function calling" mode that executes tools without your application seeing the intermediate steps. **Disable this** in a LangChain/LangGraph agent since LangGraph manages the loop:

```python
from google.genai.types import AutomaticFunctionCallingConfig

# Option A: Disable at bind time
llm_manual = llm.bind(
    automatic_function_calling=AutomaticFunctionCallingConfig(disable=True)
)

# Option B: force no tools for a specific call
llm_no_tools = llm.bind_tools(tools, tool_choice="none")
```

### Pattern 6 — The Tool Execution Loop (Manual, Recommended for Agents)

```python
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
from typing import List, Any

def run_agent_step(
    llm_with_tools,
    messages: List[Any],
    tool_map: dict,
    max_steps: int = 10
) -> List[Any]:
    """Run a single agent step: LLM call → tool execution → return updated messages."""
    
    for step in range(max_steps):
        ai_msg = llm_with_tools.invoke(messages)
        messages.append(ai_msg)
        
        # Check finish reason
        finish_reason = ai_msg.response_metadata.get("finish_reason", "")
        if finish_reason == "UNEXPECTED_TOOL_CALL":
            # Model confused — stop and return
            break
        
        if not ai_msg.tool_calls:
            # No tool calls — we have the final answer
            break
        
        # Execute all tool calls (handle parallel calls)
        tool_messages = []
        for call in ai_msg.tool_calls:
            tool_name = call["name"]
            tool_args = call["args"]
            tool_call_id = call["id"]
            
            # Validate args before execution
            if not tool_args:
                result = f"Error: No arguments provided for {tool_name}"
            elif tool_name not in tool_map:
                result = f"Error: Unknown tool {tool_name}"
            else:
                try:
                    result = tool_map[tool_name].invoke(tool_args)
                except Exception as e:
                    result = f"Error executing {tool_name}: {str(e)}"
            
            tool_messages.append(
                ToolMessage(
                    content=str(result),
                    tool_call_id=tool_call_id,
                    name=tool_name  # Critical: always set name field
                )
            )
        
        messages.extend(tool_messages)
    
    return messages
```

### Pattern 7 — Sub-Agent Tool (Orchestrator calling sub-agents)

For your specific architecture where the orchestrator calls sub-agents via `use_sub_agent_with_skill`:

```python
from pydantic import BaseModel, Field
from langchain_core.tools import tool

class SubAgentArgs(BaseModel):
    skill_name: str = Field(
        description=(
            "Name of the sub-agent skill to invoke. "
            "Available: 'qdrant_search', 'video_analysis', 'channel_metrics', 'trend_analysis'"
        )
    )
    situational_prompt: str = Field(
        description=(
            "Detailed context and instructions for the sub-agent, including: "
            "what specific information is needed, any constraints, "
            "and how the result will be used."
        )
    )

@tool(args_schema=SubAgentArgs)
def use_sub_agent_with_skill(skill_name: str, situational_prompt: str) -> str:
    """
    Delegate a task to a specialized sub-agent.

    Use this tool to invoke domain-specific agents for: searching the knowledge base,
    analyzing video content, fetching channel metrics, or performing trend analysis.
    Always provide a detailed situational_prompt so the sub-agent has full context.

    Returns:
        JSON string with the sub-agent's findings.
    """
    # Implementation dispatches to the appropriate sub-agent
    return dispatch_to_sub_agent(skill_name, situational_prompt)
```

**Why this works reliably with Gemini:**
- Only `str` types — no Union, no Optional[complex], no dict
- Explicit `args_schema` with field descriptions
- Tool name uses only underscores (no spaces)
- Clear, detailed docstring with a concrete Returns description

---

## 7. Model Recommendations for Agentic Workloads

### Current Model Lineup (May 2026)

| Model | Context | Max Output | Thinking | Best For |
|-------|---------|-----------|---------|---------|
| `gemini-2.5-flash` | 1M tokens | 65K tokens | Optional (budget 0–24K) | **Primary agent model** |
| `gemini-2.5-pro` | 1M tokens | ~8K tokens | Built-in | Complex reasoning, code, research |
| `gemini-2.5-flash-lite` | 1M tokens | ~8K tokens | No | Classification, routing, cost-critical |
| `gemini-3-pro-preview` | — | — | Yes (mandatory) | Not recommended yet (thought_signature bugs) |

### Recommendation: Use `gemini-2.5-flash` for Both Orchestrator and Sub-Agents

**Reasoning:**

1. **Thinking disabled by default (`thinking_budget=0`):** Avoids the `thought_signature` issue that breaks multi-turn tool calling with thinking enabled in LangChain.

2. **Cost-effective at scale:** At $0.30/1M input, $2.50/1M output, high-volume multi-agent invocations stay affordable.

3. **Sufficient reasoning for sub-agent dispatch:** The orchestrator's only job is to pick a skill and write a prompt — Flash handles this without Pro-level reasoning.

4. **1M context window:** Sufficient for long conversation histories with tool results.

5. **GA and stable:** The stable `gemini-2.5-flash` release doesn't have the empty-parts bug that affects preview snapshots.

**When to upgrade to `gemini-2.5-pro`:**

- A sub-agent needs to do complex multi-step reasoning (e.g., synthesizing data from multiple sources into an analytical report)
- A sub-agent works with long code analysis or legacy migration tasks
- Accuracy is more important than latency for that specific skill

**Avoid for now:**
- `gemini-2.5-flash-lite` for any agent that calls tools — too many `UNEXPECTED_TOOL_CALL` reports
- `gemini-3-*` models — `thought_signature` issue is not resolved in LangChain as of late 2025
- Preview/snapshot model IDs (`-preview-*`, `-exp-*`) in production — behavior is unstable

### Configuration Template

```python
from langchain_google_genai import ChatGoogleGenerativeAI

def make_agent_llm(model: str = "gemini-2.5-flash") -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=model,
        temperature=1.0,         # Default for 2.5+; lower values risk loops
        thinking_budget=0,       # Disable thinking to avoid thought_signature issues
        max_output_tokens=8192,
        max_retries=3,
    )

orchestrator_llm = make_agent_llm("gemini-2.5-flash")
sub_agent_llm = make_agent_llm("gemini-2.5-flash")

# For a skill that needs deeper reasoning:
reasoning_llm = make_agent_llm("gemini-2.5-pro")
```

---

## 8. Known Workarounds Cheatsheet

### Schema / Type Issues

| Problem | Workaround |
|---------|-----------|
| `Union[X, Y]` breaks schema | Use the broader single type: `float` instead of `Union[int, float]` |
| `Optional[date \| datetime]` dropped from schema | Use `str` with ISO 8601 description |
| `dict` / `Dict[str, Any]` rejected | Define explicit `BaseModel` with named fields |
| Tool name has spaces or invalid chars | `tool.name = tool.name.replace(' ', '_').lower()[:64]` before `bind_tools` |
| `additionalProperties` rejected by SDK validator | Use `response_json_schema` or update to latest `google-genai` SDK |
| Community tool missing `args_schema` | Add `MyTool.args_schema = EmptyBaseModel` |

### Multi-Tool / Routing Issues

| Problem | Workaround |
|---------|-----------|
| Model only uses first of multiple tools | Update `langchain-google-genai >= 1.0.8` |
| Model ignores tools and responds in text | Use `bind_tools(tools, tool_choice="any")` to force tool selection |
| Model calls wrong tool | Add `allowed_function_names` in `tool_config` to restrict choices |
| Can't mix native tools + custom tools | Use separate LLM instances; route at application layer |

### Streaming Issues

| Problem | Workaround |
|---------|-----------|
| Streaming delivers 1 chunk instead of tokens when tools bound | Use `invoke()` for tool-calling steps; only stream final answer |
| Parallel tool calls in streaming drops all but first (Flash) | Disable streaming: `disable_streaming="tool_calling"` or use `invoke()` |
| `on_llm_new_token` callback not firing | Use `model_kwargs={"streaming": True}` or iterate `.stream()` directly |

### LangGraph / Agent Loop Issues

| Problem | Workaround |
|---------|-----------|
| `ToolMessage.name` not set → 400 error | Set `tool_message.name = call["name"]` explicitly; use `langgraph.prebuilt.create_react_agent` |
| Gemini 2.5 Flash empty response in LangGraph | Use stable GA model ID; filter empty messages before appending to state |
| `thought_signature` missing (thinking models) | Set `thinking_budget=0`; always pass whole `AIMessage` back unmodified |
| `contents.parts must not be empty` | Guard: check `len(ai_msg.content) > 0` before appending to state |
| `UNEXPECTED_TOOL_CALL` finish reason | Check `finish_reason` after each invoke; re-call without tools if triggered |
| Context caching + tools breaks | Pre-define tools in `CachedContentConfig`; don't use `bind_tools()` with cached models |

### Automatic Function Calling

| Problem | Workaround |
|---------|-----------|
| SDK auto-executes tools without your control | Bind `AutomaticFunctionCallingConfig(disable=True)` |
| Model skips tools in some turns | Provide `tool_choice="any"` or strengthen the system prompt |
| Infinite tool loop | Cap at `MAX_STEPS=10`; check `finish_reason != "STOP"` |

### Structured Output

| Problem | Workaround |
|---------|-----------|
| `.with_structured_output()` conflicts with tool use | Use separate model calls; don't combine structured output + tools |
| Structured output streaming crashes with `+=` | Use `.update()` (dict merge) instead of `+=` |
| `with_structured_output()` ignores `google_search` | Use `.bind(response_mime_type="application/json", response_schema=...)` instead |

---

## 9. Sources

### Official Documentation
- [Google AI: Function Calling Documentation](https://ai.google.dev/gemini-api/docs/function-calling)
- [Google Cloud Vertex AI: Introduction to Function Calling](https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/function-calling)
- [LangChain: ChatGoogleGenerativeAI Integration Docs](https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai)
- [LangChain: ChatGoogleGenerativeAI Reference](https://reference.langchain.com/python/langchain-google-genai/chat_models/ChatGoogleGenerativeAI)
- [Gemini 2.5 Flash on Vertex AI](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5-flash)
- [Gemini 2.5 GA Announcement](https://cloud.google.com/blog/products/ai-machine-learning/gemini-2-5-flash-lite-flash-pro-ga-vertex-ai)

### GitHub Issues (langchain-google)
- [#369 — Gemini only accesses 1 tool when multiple given](https://github.com/langchain-ai/langchain-google/issues/369)
- [#463 — Union types fail with Vertex AI](https://github.com/langchain-ai/langchain-google/issues/463)
- [#711 — Tool calling broken with legacy agent (ToolMessage.name)](https://github.com/langchain-ai/langchain-google/issues/711)
- [#872 — thinking_budget parameter for Gemini 2.5 Flash](https://github.com/langchain-ai/langchain-google/issues/872)
- [#1079 — SlackToolkit incompatibility with Gemini](https://github.com/langchain-ai/langchain-google/issues/1079)
- [#1150 — Streaming callback not working](https://github.com/langchain-ai/langchain-google/issues/1150)
- [#1216 — anyOf schema alongside other fields](https://github.com/langchain-ai/langchain-google/issues/1216)
- [#1289 — with_structured_output ignores google_search](https://github.com/langchain-ai/langchain-google/issues/1289)
- [#1332 — Tool name validation failure](https://github.com/langchain-ai/langchain-google/issues/1332)
- [#1364 — thought_signature missing with create_react_agent + Gemini 3](https://github.com/langchain-ai/langchain-google/issues/1364)
- [#1528 — Context caching incompatibility with tools](https://github.com/langchain-ai/langchain-google/issues/1528)

### GitHub Issues (LangGraph / LangChain)
- [langgraph #4780 — Gemini 2.5 fails with LangGraph Agent](https://github.com/langchain-ai/langgraph/issues/4780)
- [langgraph #4877 — Streaming broken when tools bound](https://github.com/langchain-ai/langgraph/issues/4877)
- [langchain #29418 — Tool calling broken with legacy agent](https://github.com/langchain-ai/langchain/issues/29418)

### GitHub Issues (LangChain.js — relevant patterns apply to Python too)
- [langchainjs #8454 — Parallel tool call parsing bug in streaming mode (Flash)](https://github.com/langchain-ai/langchainjs/issues/8454)
- [langchainjs #8589 — UNEXPECTED_TOOL_CALL error](https://github.com/langchain-ai/langchainjs/issues/8589)
- [langchainjs #10819 — Cannot mix native + custom tools](https://github.com/langchain-ai/langchainjs/issues/10819)

### GitHub Issues (google-genai SDK)
- [python-genai #1815 — additionalProperties rejected by SDK validator](https://github.com/googleapis/python-genai/issues/1815)

### Articles and Guides
- [Gemini Function Calling in Production: What Most Tutorials Skip (Mar 2026)](https://medium.com/@vinothkkumar24/gemini-function-calling-in-production-what-most-tutorials-skip-f8908001f0f2)
- [OpenAI vs Gemini Function Calling](https://medium.com/@smallufo/openai-vs-gemini-function-calling-a664f7f2b29f)
- [Function Calling & Tool Use: Complete Guide 2026](https://ofox.ai/blog/function-calling-tool-use-complete-guide-2026/)
- [Phil Schmid: Gemini LangChain Cheatsheet](https://www.philschmid.de/gemini-langchain-cheatsheet)
- [Phil Schmid: Gemini Function Calling Guide (2.0 Flash)](https://www.philschmid.de/gemini-function-calling)
- [LangChain Forum: Forcing tool use with Gemini 2.5 Flash](https://forum.langchain.com/t/how-to-force-llm-model-gemini-2-5-flash-to-use-tool/1443)
- [LangChain Forum: LangGraph ignores tool outputs with Gemini](https://forum.langchain.com/t/langgraph-seems-to-ignore-tool-outputs-with-gemini-models/2629)
- [LangChain Forum: Disable automatic function calling](https://forum.langchain.com/t/how-to-disable-automatic-function-calling-with-chatgooglegenerativeai/3352)
