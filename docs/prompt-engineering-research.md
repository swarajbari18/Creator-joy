# Prompt Engineering Research: Writing Skill Files for CreatorJoy

**Purpose:** Developer reference for rewriting all skill `.md` files used as system prompts for CreatorJoy sub-agents.  
**Date compiled:** May 2026  
**Applies to:** LangChain sub-agents powered by Gemini, receiving skill `.md` as system prompt + orchestrator situational prompt as human message.

---

## The Problem with the Current Skill Files

The current `search_skill/skill.md` is written as a specification document, not an LLM system prompt. It uses section headers like "**Section 1 — Philosophy**" and contains a reference-table format that reads like API documentation written for a human developer. The LLM receiving this prompt is not a developer reading docs — it is an instruction-following model that needs to be told who it is, what it does, and how it behaves, in that order.

The specific problems:

- **No identity statement.** The file never tells the agent what it *is* or what its goal is. It jumps straight into rules about tools.
- **Specification framing, not behavioral framing.** "Set `filters` with one or more `StructuralFilters` fields" describes a data structure, not behavior. The agent doesn't need a type signature lecture — it needs to know what to *do* and *when*.
- **The "worked examples" section reads like test cases.** The formatting (`Example 1:`, `Example 2:`) makes them look like unit tests rather than behavioral demonstrations. The LLM does not infer "this is the format I should follow" from test-case formatting.
- **No output shape instruction.** The file describes what the tool does, but never tells the agent what its response to the user should look like.
- **Constraints buried in prose.** "Never use semantic search to find things expressible as field values" is buried in Section 6, which the model may underweight relative to earlier content.

---

## Part 1: What Makes a Good System Prompt

### The Mental Model

Think of the LLM as "a brilliant but new employee who lacks context on your norms and workflows." The system prompt is the onboarding document. It tells the model who it is, what domain it operates in, what it is allowed to do, how to format its work, and when to ask for help.

More precisely, by 2026 the field has converged on treating the system prompt as a **context engineering artifact** — not a set of instructions, but a carefully assembled context window that gives the model everything it needs to operate reliably on the task class it will face.

The key design tension is altitude: prompts that are too vague ("be helpful and accurate") give the model no actionable guidance. Prompts that are too prescriptive ("if X then do Y, else if Z then do W") create brittle, maintenance-heavy logic. The goal is instructions "specific enough to guide behavior effectively, yet flexible enough to provide the model with strong heuristics." (Anthropic, Effective Context Engineering, 2025)

### The Canonical Component Order

Research and practitioner consensus in 2025-2026 has converged on this ordering. The rationale is that models weight earlier content more heavily, and information "buried in the middle" suffers 30%+ accuracy degradation compared to content at the start or end (the "lost in the middle" problem).

**1. Identity / Role (2-4 sentences)**  
Who this agent is. What it specializes in. What its primary goal is. This anchors all subsequent behavior. Vague role statements like "You are a helpful assistant" are insufficient. Specificity matters: "You are a video segment analyst for CreatorJoy. Your job is to answer questions about creator video content by searching a structured database of video segments and returning evidence-grounded answers."

**2. Behavioral Stance (3-6 bullet points or short sentences)**  
Core behavioral commitments that apply to everything this agent does: grounding requirements, citation style, what to do when data is missing, what the agent should never do. These are the non-negotiable operating rules. They belong near the top, not in a closing section.

**3. Tool Use Policy (1 paragraph + decision rules)**  
When to use tools, in what order, with what priority rules. For agents with multiple tools or multiple modes, explicit heuristics prevent inconsistent tool selection. "When both structural filters AND a semantic query exist, use Mode 3" is correct — but it should be in the context of "here is how you decide which tool/mode to call", not buried after a table of field types.

**4. Output Format (explicit, concrete)**  
What the agent's response to the user should look like. Not vague ("structured output") but specific: headers, field names, citation style, whether to use tables, what to do when results are empty. If output is consumed programmatically downstream, provide the exact JSON schema or field structure.

**5. Few-Shot Examples (2-5, well-chosen)**  
Demonstrations of the expected input → output behavior. These are the highest-signal component after the identity statement. They show not just *what* to do but also *structure, tone, and edge-case handling*. Good examples outperform exhaustive rule lists because they communicate the gestalt of expected behavior.

**6. Hard Constraints / Guard Rails (visually separated)**  
The absolute limits. Things the agent must never do regardless of instruction. These need visual separation (a `---` divider, a `<constraints>` tag, or a bold header) so they are not skimmed over as prose.

### Token Budget

Keep system prompts in the 400-800 token range for sub-agents with focused tasks. Research shows reasoning performance degrades around 3,000 tokens. A customer support agent with a 3,000-token system prompt performed measurably worse at multi-step reasoning than the same model with a 400-token version. Expand beyond 800 tokens only when the task genuinely requires it (large field reference tables, many example types).

The optimal compression technique: convert soft prose to labeled directives. "You should try to always make sure that you are grounding your claims in the data" (22 tokens) → "Ground every claim in a segment_id and timecode. No exceptions." (11 tokens, higher compliance).

---

## Part 2: Skill / Persona Prompts for Specialist Agents

### What a Skill Prompt IS

A skill prompt is a reusable, saved prompt that defines a persistent specialist persona. It is not a job title. It is a complete behavioral specification for one mode of operation. The analogy from current practitioner writing: "A Skill is essentially a saved, reusable prompt that defines a persistent persona, with the role and context and constraints baked into a 'system prompt' that runs automatically." (Doug Seven, Agentic AI 101, April 2026)

In the CreatorJoy architecture, skill `.md` files are exactly this: the system prompt for a dynamically assembled sub-agent. The sub-agent receives the skill file as its entire identity and operating context.

### The Six-Component Skill Framework

Current best practice for skill prompts organizes them around six elements (documented by Doug Seven and confirmed by Anthropic's sub-agent architecture guidance):

| Component | What it defines | Example for SearchSkill |
|---|---|---|
| **Role** | Identity, approach, disposition | "Video segment analyst specializing in structured + semantic retrieval from creator content databases" |
| **Scope** | What it does AND what it doesn't do | "You search and return data. You do not analyze, editorialize, or predict. You do not answer questions that have no data support." |
| **Context** | Situational intelligence about environment | "You operate on a Qdrant vector store containing timestamped video segments with production metadata fields." |
| **Tone** | Communication register | "Precise and data-forward. Return values, not narratives. Speak in terms of fields, timecodes, and segment IDs." |
| **Format** | Output structure | "For FETCH results: segment_id, timecode range, relevant field values. For COUNT: single integer with the query echoed. For GROUP_BY: field value → count table." |
| **Error Handling** | What to do when input is unclear or data is missing | "If no results are found, say so explicitly. Do not fabricate alternatives. Do not broaden the search without saying you are doing so." |

Most skill files in the wild write Role and sometimes Scope but skip Context, Tone, Format, and Error Handling entirely. The last three are where most production failures occur.

### Persona Effectiveness: What the 2026 Research Says

A critical finding from USC research (Boosting Alignment vs. Accuracy, published March 2026, covered by The Register) undermines the "you are an expert" framing that many skill prompts use:

- **Expert persona claims hurt knowledge-retrieval tasks.** When the LLM is told "you are an expert in X," it activates instruction-following mode rather than knowledge-retrieval mode. On MMLU discriminative tasks, expert persona variants showed 68.0% accuracy vs. 71.6% baseline — a measurable degradation.
- **Expert persona claims help alignment-dependent tasks.** For writing, formatting, safety refusals, and role-playing, personas improve performance.
- **The practical rule:** Do not open a skill prompt with "You are an expert database engineer" for a retrieval skill. That framing actively impairs the factual/technical performance you need. Instead, define the *role in context* ("You are a video segment analyst operating on structured creator data") rather than making expertise claims ("You are an expert analyst").

The right framing for a specialist skill is **functional specificity**, not **expertise declaration**. Tell the model what it does and what data it operates on — not how smart it is at doing it.

### Skill Stacking in CreatorJoy

The system loads multiple skill files when the orchestrator's classifier detects multi-intent queries. Two skill blocks stack in the system prompt. Implications for skill file writing:

- Each skill must be **self-contained** — it cannot assume another skill's context is present.
- Skills should define their contribution by **output contract**, not by exhaustive field coverage. Two stacked skills that both try to cover everything produce contradictory instructions.
- Guard rails in each skill should be **additive**, not conflicting. If SearchSkill says "never fabricate data" and ProductionAuditSkill says "always report exact observed values," these stack cleanly. If SearchSkill says "keep responses brief" and TwoVideoComparisonSkill says "return structured side-by-side tables," they conflict.

---

## Part 3: Writing Instructions That Are Actually Followed

### Why Instructions Get Ignored

LLMs do not process instructions like a program executing code. They weight instructions by position, repetition, and specificity. The three main reasons instructions fail:

**1. Vagueness.** "Be concise" and "be accurate" are not actionable. The model cannot evaluate whether it is being concise enough. These soft directives produce soft compliance. The fix: operationalize the constraint. "Responses should not exceed 300 words unless the data requires a table that is longer" is followable. "Be concise" is not.

**2. Burial.** Critical constraints placed in the middle of a long system prompt suffer the lost-in-the-middle effect. Research confirms 30%+ accuracy degradation for content positioned in the middle of context windows. Put non-negotiable constraints at the beginning or at the very end, not in a middle section.

**3. Instruction overload.** There is a threshold beyond which adding more instructions begins to hurt compliance with existing ones. Adding constraints like "be concise," "avoid speculation," and a strong persona modifier simultaneously can cause the model to omit critical information or oversimplify. The 2026 practitioner consensus: "Add constraints only to address actual output gaps, not hypothetical concerns." Start minimal. Expand only when testing reveals a specific failure mode.

### Formatting: XML vs. Markdown vs. Plain Prose

The research is clear and model-specific:

**XML tags for Claude.** Anthropic's Claude is trained to treat XML tags (`<instructions>`, `<context>`, `<example>`, `<constraints>`) as semantic delimiters. They create genuine parsing boundaries that improve instruction following. XML is also superior for prompt injection defense: `<system_instruction>` tags clearly distinguish trusted instructions from potentially untrusted user input.

**Markdown headings for Gemini.** Gemini responds well to hierarchical Markdown structure. Google's own documentation recommends Markdown headers for organizing Gemini prompts, with constraints "in the System Instruction or at the very top."

**For CreatorJoy sub-agents (LangChain + Gemini):** Use Markdown headers (`##`) for top-level sections and use XML-style tags for inline delimiting of specific elements (examples, constraints, field references). This hybrid approach is compatible with Gemini's strong Markdown parsing and provides the semantic clarity of XML for critical sections.

**Positive framing outperforms negative framing.** "Only use structural search when the query can be expressed as a field value" outperforms "Never use semantic search for structural queries" — negation forces the model to process the unwanted concept first. Frame instructions as what to DO, not what NOT to do. Reserve "never" and "do not" for absolute hard constraints only.

**Numbered lists for multi-step procedures.** When an instruction has sequential steps, number them. Unordered bullet points are fine for properties; ordered steps need ordering signals.

**Aggressive caps and bold formatting reduce compliance.** Research cited in the Thomas Wiegold 2026 guide and confirmed by Gemini 3-specific guidance: "CRITICAL!", "MUST DO THIS", "EXTREMELY IMPORTANT" phrasing reduces output quality for Claude and Gemini. These models respond better to calm, direct language. Use caps/bold only for hard guard rail labels that need visual separation, not for emphasis within prose.

### The Instruction Placement Priority Order

Based on the lost-in-the-middle research and practitioner consensus:

```
[Position 1: Beginning]     → Identity, Core Behavioral Stance, Non-negotiable Rules
[Position 2: After Identity] → Tool Use Policy, Decision Heuristics  
[Position 3: Middle]        → Field References, Worked Examples (safe to bury here)
[Position 4: Near End]      → Output Format Specification
[Position 5: Very End]      → Hard Guard Rails (restated or first stated)
```

If a constraint is truly non-negotiable, state it both at the beginning (in behavioral stance) and at the end (in guard rails). The redundancy is intentional and justified by the memory-like weighting of early and late content.

---

## Part 4: Tool Use Guidance in System Prompts

### Core Principle: Tool Descriptions Are Part of Your Prompt

Tool definitions are loaded into the agent's context on every call. They consume tokens. They shape behavior. Writing a good system prompt and bad tool descriptions produces a bad agent. The tool name, description, and parameter schema are as important as any instruction you write.

From Anthropic's engineering guide on writing tools for agents (2025): tool descriptions should be written "as if the model were a developer using them" — implicit knowledge made explicit, zero ambiguity about when to use this tool vs. another.

### How to Write Tool Selection Heuristics

Do not just list tools. Establish **priority rules and decision heuristics**. Without explicit heuristics, agents default inconsistently — often to the most capable (and expensive) option when cheaper ones would suffice.

Pattern: **"Use X when [condition], use Y when [condition], use Z only when [condition]."**

Bad (current SearchSkill approach):
> "Mode 2 — Semantic: Set `nl_query` to the natural language query. Leave `filters=None`. Use only when the query cannot be expressed as field values."

This is technically correct but expressed as a specification. The model reads specifications differently than behavioral instructions.

Better:
> "Your default retrieval mode is structural (Mode 1). Every query first — ask: can this be answered with field values? Shot types, boolean flags, camera angles, speaker IDs are always structural. If yes, use Mode 1 with the appropriate filters. Only escalate to semantic (Mode 2) when the question asks about meaning, tone, emotion, or intent that cannot be expressed as a field value. Use hybrid (Mode 3) when the query has both a structural constraint AND a meaning/semantic component."

The difference: the better version establishes a decision flow the model can follow, not a data structure specification the model must translate into behavior.

### The Token Efficiency Rule for Tool Definitions

Tool definitions consume input tokens on every call. The recommendation from Anthropic's production guidance: be concise but descriptive. Avoid bloated tool sets. When you have 30+ tools, use tool search / dynamic tool loading rather than dumping all definitions into context.

For CreatorJoy sub-agents, each skill file should only reference the tools that skill actually uses. A SearchSkill agent with `search_segments` should not have the full tool definitions for analysis tools — those belong in other skill files.

### Error Recovery Instructions

A 2026 pattern from Paxrel's agent prompt engineering guide: distinguish recoverable errors (handle autonomously, retry with modified parameters) from unrecoverable ones (stop, surface the problem explicitly). Without these instructions, agents either silently fail or produce fabricated results to fill the gap.

For SearchSkill specifically:
- Empty result set from a structural search = recoverable. Try broadening one filter. If still empty, report "no segments match [criteria]."
- Empty result set after broadening = unrecoverable. Report it explicitly, do not switch to semantic search as a fallback without saying so.
- Tool call failure = unrecoverable. Do not fabricate a response. Report the error.

### Pre-Tool Reasoning

Gemini 3 responds well to an explicit pre-tool reasoning requirement: state *why* you are calling this tool, *what* data you expect, and *how* it solves the current question. This activates chain-of-thought behavior that improves tool selection accuracy. It also makes the agent's reasoning auditable.

Include in the skill file: "Before each tool call, briefly state your retrieval plan: which mode you are using and why. One sentence is enough."

---

## Part 5: Few-Shot Examples

### When They Help

Few-shot examples remain high-value in 2026 for task-specific behavior shaping. They are the most efficient way to communicate:

- The expected output structure
- Tone and precision level
- Edge-case handling (what to do when results are partial, ambiguous, or empty)
- The level of verbosity (an example response length signals expected length more reliably than a word count instruction)

Google's prompt engineering whitepaper (2025-2026) explicitly recommends against zero-shot for Gemini: "always include few-shot examples." This is a Gemini-specific finding — GPT-5 handles zero-shot more reliably.

### Format and Placement

**Wrap examples in XML-like tags.** Even in Markdown-primary prompts, using `<example>` and `</example>` tags creates clear parsing boundaries that distinguish "this is a demonstration" from "these are instructions."

**Place examples AFTER instructions, BEFORE hard constraints.** The canonical order is: identity → behavioral rules → tool policy → examples → output format → guard rails. Examples in the middle of instructions confuse the boundary between "rules" and "demonstrations."

**Structure each example as: input → reasoning → output.** For retrieval agents especially, showing the reasoning step ("This is a structural query because shot_type is a keyword field") trains the decision process, not just the output shape.

**Use 3-5 examples, covering:** (a) a representative normal case, (b) an edge case or ambiguous case, (c) an empty/no-result case, (d) a multi-constraint case. Do not cover every possible case — curate for diversity of type, not exhaustiveness.

**Example quality over quantity.** Two examples that clearly demonstrate the behavioral boundary between structural and semantic mode are more valuable than fifteen examples that only cover happy-path structural queries.

### The Bad Example in Current SearchSkill

The current "15 Worked Examples" section is exhaustive but poorly formatted. `Example 15: "Never use semantic search to find shot_type=MCU — that's a structural query."` — this is an anti-pattern instruction disguised as an example. Anti-patterns belong in guard rails, not in the examples section. Examples should only show desired behavior.

---

## Part 6: Anti-Patterns to Avoid

### Anti-Pattern 1: Specification-Document Framing

Writing skill files like API documentation. Field type tables, method signatures, section numbering like "**Section 3 — Operations Reference**" — these are fine in a developer README, but they're poor system prompt format. LLMs follow behavioral instructions more reliably than they follow specification documents.

**Fix:** Replace specification language with behavioral language. Not "Set `nl_query` to the natural language query" but "Use the natural language query field when the question asks about meaning, tone, or emotion."

### Anti-Pattern 2: Role Without Constraints

Defining what the agent IS without defining what it must NOT do. This leaves the agent free to improvise in dangerous ways. A SearchSkill that knows it searches video segments but is never told "you do not analyze, you do not give recommendations, you do not extrapolate beyond the data" will eventually do all three.

**Fix:** Every role definition must be paired with an explicit scope boundary. What it does AND what it does NOT do.

### Anti-Pattern 3: Vague Behavioral Directives

"Be accurate," "be concise," "be thorough" — these are aspirational, not operational. The model cannot evaluate whether it is accurate enough. These phrases consume tokens and produce soft, inconsistent compliance.

**Fix:** Operationalize every behavioral directive. "Be accurate" → "Every claim must be supported by a retrieved segment_id and timecode. If you cannot cite a source, do not make the claim."

### Anti-Pattern 4: Instruction Overload

Adding more and more constraints thinking it will make the agent more reliable. Beyond a threshold (roughly 800-1000 tokens for sub-agents with focused tasks), additional instructions degrade compliance with existing ones. The attention mechanism's capacity is finite.

**Fix:** Add constraints only to fix observed failures. If a constraint addresses a failure mode you have not actually seen, cut it. The minimum set of constraints that produces correct behavior is the correct prompt.

### Anti-Pattern 5: Expertise Claims for Retrieval Tasks

"You are an expert retrieval agent," "As a master search specialist..." — these persona-claiming phrases are counterproductive for knowledge-retrieval and data-access tasks. The USC 2026 research shows this framing activates instruction-following mode over knowledge-retrieval mode, measurably degrading accuracy (68.0% vs. 71.6% baseline).

**Fix:** Define functional role in context, not expertise. "You are the retrieval component of the CreatorJoy analysis system. Your job is to query the video segment database and return well-grounded results." No expertise claims.

### Anti-Pattern 6: Anti-Patterns Embedded in Examples

Including "Example 15: NEVER do X" — using the examples section to state constraints. Examples should only show desired behavior. Anti-patterns belong in the guard rails section with visual separation.

### Anti-Pattern 7: Burying Critical Constraints in the Middle

Placing "Never use semantic search to find things expressible as field values" in the last section of the file. By the time the model reaches this, the early instruction set has already established patterns. Critical decision rules must appear early.

### Anti-Pattern 8: Irresponsible Context Stuffing

Dumping entire field reference tables into the system prompt when only a subset of fields will be queried 90% of the time. This wastes context budget and dilutes instruction weight.

**Fix:** Include the most-used fields inline. Move the full reference table to a separate appendix section clearly marked as "reference only" or consider loading it dynamically via a tool when the agent actually needs to enumerate fields.

### Anti-Pattern 9: No Output Format Specification

Writing detailed instructions about how to retrieve data without specifying what the agent's response to the user should look like. The retrieval is perfect, the output is a prose paragraph with data inlined arbitrarily.

**Fix:** Every skill file must include a concrete output format section with examples of what a response looks like for each operation type (FETCH, COUNT, GROUP_BY, SUM_duration).

### Anti-Pattern 10: Single-Task Overloading

Putting retrieval instructions, analysis instructions, and response-formatting instructions all in one skill. This divides the model's attention and produces lower quality at all three. The marvelous-mlops analysis: "Break the problem into smaller, atomic pieces. Instead of one large prompt asking for everything, use several smaller, focused prompts."

**Fix:** SearchSkill retrieves and reports. It does not analyze or recommend. Analysis belongs in separate skill files.

---

## Part 7: Applying All of This to CreatorJoy Skill Files

### The Architecture Context

Each skill file is the **complete system prompt** for a LangChain sub-agent. The sub-agent receives:
- System message: the skill `.md` file
- Human message: the orchestrator's `situational_prompt` (the specific task for this invocation)

This means the skill file cannot assume any additional context. It has to be self-contained. It does not know what the user asked — only the situational prompt (which is the orchestrator's interpretation of the user's request).

### Recommended Skill File Template

```markdown
## Role

[2-4 sentences: who this agent is, what it does, what data it operates on, what its primary goal is.
NO expertise claims. Functional specificity only.]

## Behavioral Stance

[5-7 bullets: the non-negotiable operating rules. Grounding requirements. Citation style. 
What to do when data is missing. What this agent does NOT do.]

## Tool Decision Rules

[1-2 paragraphs: when to use each tool/mode, in what order, with what priority.
Written as a decision flow the model can follow, not as a specification document.]

## Output Format

[Concrete, specific. What does a response look like for each query type?
Use examples of actual output structure, not descriptions of it.]

<examples>

<example>
Query: [realistic question from the orchestrator's situational_prompt]
Retrieval Plan: [one sentence: which mode and why]
Tool Call: [the actual call parameters]
Response: [what the agent returns to the orchestrator]
</example>

[2-4 more examples covering: normal case, edge case, empty result, multi-constraint case]

</examples>

---
## Guard Rails

[Hard limits. Visually separated from the rest. These override everything else.
State as: "Never X. Never Y." Reserve this language for genuine absolutes.]
```

### Specific Rewrites for SearchSkill

The current SearchSkill's core content is correct — the three modes are right, the field table is right, the examples are mostly right. The problems are structural and presentational. The rewrite should:

1. **Open with a role statement** that places the agent in context and declares its output contract.
2. **Move behavioral stance** (the grounding requirement, the structural-first rule) to the top, not buried in sections.
3. **Replace the mode specification table** with a decision flow paragraph that the model follows.
4. **Keep the field table** but mark it explicitly as "reference only — consult when you need to construct filters" rather than as a primary instruction.
5. **Reformat the examples** into `<example>` blocks with retrieval plan + tool call + response structure.
6. **Move "common mistakes"** section content into the guard rails section at the bottom, with visual separation.
7. **Add an output format section** that shows exactly what FETCH, COUNT, GROUP_BY, and SUM_duration responses look like.

### The Orchestrator's Situational Prompt

Because the human message is the orchestrator's `situational_prompt` rather than the raw user query, skill files should be written assuming the input is already a well-scoped task description, not a vague conversational query. This means:

- The skill can assume intent has been classified (it knows it's the SearchSkill because the orchestrator chose it).
- The skill should focus on execution quality, not intent interpretation.
- The skill can be more terse on disambiguation — the orchestrator handles that.

However: the skill must still handle the case where the situational prompt is ambiguous or asks for data that does not exist. The orchestrator is not infallible.

### Skill File Length Budget

| Skill Type | Recommended Token Range | Notes |
|---|---|---|
| Single-purpose retrieval (SearchSkill) | 400-600 tokens | Keep lean; field reference is appendix |
| Multi-mode analysis (ProductionAudit) | 500-700 tokens | More output format variation |
| Comparison skills (TwoVideoComparison) | 600-800 tokens | Needs parallel retrieval examples |
| Series/pattern skills (SeriesAnalysis) | 600-750 tokens | Needs multi-video aggregation examples |
| Stacked skill pair (any two combined) | 800-1200 tokens total | Monitor for degradation; test carefully |

### Model-Specific Note: Gemini Sub-Agents

CreatorJoy's sub-agents run on Gemini. Gemini-specific guidance from the 2026 research:

- **Always include few-shot examples.** Zero-shot is explicitly not recommended for Gemini (unlike GPT-5 which handles it well). Include 3-5 examples in every skill file.
- **Place specific questions/task instructions at the END of data blocks.** For skill files that include large reference tables, put the tool decision rules and behavioral stance BEFORE the table, and include a bridging instruction at the end ("Given the field reference above, use the following decision rules...").
- **Use Markdown headings for section structure.** Gemini's document understanding is strongest with hierarchical Markdown.
- **Use XML tags for examples and constraints.** `<example>`, `<constraints>` blocks within the Markdown provide semantic clarity for critical sections.
- **No aggressive formatting caps.** Gemini's Gemini 3 guidance explicitly warns against "CRITICAL!", "MUST", all-caps emphasis. Use calm, direct language.
- **Short constraint-first.** Behavioral constraints belong "in the System Instruction or at the very top of the prompt."

---

## Part 8: Sources and References

All findings in this document are sourced from research and practitioner writing published in 2025-2026.

**System Prompt Structure and Context Engineering**
- Anthropic Engineering Blog — "Effective Context Engineering for AI Agents" (2025): https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Promptingguide.ai — "Context Engineering Guide": https://www.promptingguide.ai/guides/context-engineering-guide
- Lakera — "The Ultimate Guide to Prompt Engineering in 2026": https://www.lakera.ai/blog/prompt-engineering-guide
- Thomas Wiegold — "Prompt Engineering Best Practices 2026": https://thomas-wiegold.com/blog/prompt-engineering-best-practices-2026/

**Skill and Persona Prompting**
- Doug Seven — "Agentic AI 101: From Prompts to Skills to Agents" (April 2026): https://dougseven.com/2026/04/23/agentic-ai-101-from-prompts-to-skills-to-agents/
- Paxrel — "AI Agent Prompt Engineering: 10 Patterns That Actually Work (2026)": https://paxrel.com/blog-ai-agent-prompts

**Persona Effectiveness Research**
- arXiv 2603.18507 — "Expert Personas Improve LLM Alignment but Damage Accuracy: Bootstrapping Intent-Based Persona Routing with PRISM" (March 2026): https://arxiv.org/html/2603.18507v1
- The Register — "Telling an AI model that it's an expert makes it worse" (March 2026): https://www.theregister.com/2026/03/24/ai_models_persona_prompting/

**Instruction Following and Formatting**
- Medium / Tech for Humans — "Effective Prompt Engineering: Mastering XML Tags": https://medium.com/@TechforHumans/effective-prompt-engineering-mastering-xml-tags-for-clarity-precision-and-security-in-llms-992cae203fdc
- arXiv 2411.10541 — "Does Prompt Formatting Have Any Impact on LLM Performance?" (2025): https://arxiv.org/html/2411.10541v1
- OpenAI Developer Community — "Prompt Anti-Patterns — When More Instructions May Harm Model Performance": https://community.openai.com/t/prompt-anti-patterns-when-more-instructions-may-harm-model-performance/1372460

**Tool Use Guidance**
- Anthropic Engineering Blog — "Writing effective tools for AI agents": https://www.anthropic.com/engineering/writing-tools-for-agents
- Composio — "Tool Calling Explained: The Core of AI Agents (2026 Guide)": https://composio.dev/content/ai-agent-tool-calling-guide
- Promptingguide.ai — "Function Calling in AI Agents": https://www.promptingguide.ai/agents/function-calling

**Few-Shot Examples**
- PromptHub — "The Few Shot Prompting Guide": https://www.prompthub.us/blog/the-few-shot-prompting-guide
- Comet ML — "Few-Shot Prompting for Agentic Systems: Teaching by Example": https://www.comet.com/site/blog/few-shot-prompting/
- mem0.ai — "Few-Shot Prompting: Everything You Need to Know in 2026": https://mem0.ai/blog/few-shot-prompting-guide

**Anti-Patterns**
- Medium / Hugo Bowne-Anderson — "Patterns and Anti-Patterns for Building with LLMs": https://medium.com/marvelous-mlops/patterns-and-anti-patterns-for-building-with-llms-42ea9c2ddc90
- Treyworks — "Common Prompt Engineering Mistakes to Avoid in 2026": https://treyworks.com/common-prompt-engineering-mistakes-to-avoid/
- arXiv 2509.14404 — "A Taxonomy of Prompt Defects in LLM Systems": https://arxiv.org/html/2509.14404v1

**Gemini-Specific Guidance**
- Phil Schmid — "Gemini 3 Prompting: Best Practices for General Usage": https://www.philschmid.de/gemini-3-prompt-practices
- Google AI — "Prompt design strategies | Gemini API": https://ai.google.dev/gemini-api/docs/prompting-strategies

**Multi-Agent Skill Architecture**
- LangChain Blog — "Choosing the Right Multi-Agent Architecture": https://www.langchain.com/blog/choosing-the-right-multi-agent-architecture
