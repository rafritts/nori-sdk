# Overview

Nori is the "Spring Boot" of agentic frameworks — opinionated defaults that work in production, with escape hatches when you need to override them. The name comes from the seaweed that holds sushi together: the framework that holds the model, tools, loop, narration, and output surface into one coherent thing.

Most agentic frameworks (LangChain, LlamaIndex, OpenAI Agents SDK, CrewAI) give you plumbing but no tools. You end up rebuilding bash, file patching, and web search yourself, independently, every time. Nori ships all of it.

## Interface

The API should feel familiar to anyone who has used an existing agentic framework:

```python
from nori import Agent
from nori.tools import Bash, FilePatching, WebSearch, Memory

agent = Agent(
    name="Assistant",
    model="gpt-4o",
    instructions="You are a helpful assistant",
    tools=[Bash, FilePatching, WebSearch, Memory],
    narration=True,
)

agent.narrator_prefix = "[::] "
agent.on_narration = lambda msg: print(msg)
agent.running_context_summary = True
```

## Completions

Nori uses the **OpenAI message format** as its canonical internal representation. Conversation history is a plain `list[dict]` — no wrapper types, just the raw format any OpenAI SDK user already knows:

```python
{"role": "user", "content": "..."}
{"role": "assistant", "content": "...", "tool_calls": [...]}
{"role": "tool", "tool_call_id": "...", "content": "..."}
```

All completions go through `AsyncOpenAI` from the `openai` package. Because `AsyncOpenAI` accepts a `base_url`, Nori is provider-agnostic in practice — point it at OpenAI, Anthropic's compatibility endpoint, Ollama, Groq, or anything else that speaks the format:

```python
agent = Agent(
    model="gpt-4o",
    api_key="...",           # falls back to OPENAI_API_KEY env var
    base_url="https://...",  # optional, defaults to OpenAI
)
```

The loop is fully async. Tool calls within a turn are fanned out concurrently with `asyncio.gather`. The `openai` package handles streaming, retries, and timeouts — Nori does not reimplement these.

## The Agentic Loop

Nori runs a **tool-calling loop**: the model receives a message, responds with zero or more tool calls, those tools execute, their results are appended to the conversation, and the loop repeats until the model produces a turn with no tool calls. That final turn is the agent's response.

```
user message
    │
    ▼
┌─────────────────────────────────────┐
│  model turn                         │
│                                     │
│  narration (optional)               │
│  tool_call(A), tool_call(B), ...    │◄──┐
└─────────────────────────────────────┘   │
    │                                     │
    ▼                                     │
execute tools (parallel where possible)  │
    │                                     │
    ▼                                     │
append tool results to conversation ──────┘
    │
    ▼ (no tool calls)
final response
```

**Parallel execution.** When the model emits multiple tool calls in a single turn, Nori runs them concurrently and returns all results before the next model turn. Tools that have side effects or data dependencies are the model's responsibility to sequence — Nori fans out whatever the model asks for.

**Agentic tools.** Some built-in tools (e.g. WebSearch) are themselves agents — they accept a goal, run their own inner loop, and return a synthesized result. To the outer agent, an agentic tool looks identical to a native tool: it's just a function call that returns a string. The inner loop is fully encapsulated.

**Termination.** The loop ends when the model produces a turn with no tool calls. There is no explicit "done" signal from the model — absence of tool calls *is* the signal. The framework also enforces a configurable `max_turns` ceiling (default: 50) to prevent runaway loops. Hitting `max_turns` raises `MaxTurnsExceeded`.

**Turn structure.** Each turn in the conversation is one of:
- `user` — initial message or injected content (tool results, context summaries)
- `assistant` — model output: text, narration, and/or tool calls
- `tool` — result of a tool execution, keyed to the call that produced it

The running context summary and scratchpad are injected as `user`-role system messages at the top of the conversation, not interleaved with the turn history.

## Batteries Included Tools

Tools ship with Nori and are imported directly. They come in two flavors:

**Native** — direct function call, returns a result:
- Bash (sandboxed, with escape hatch)
- File edit / file patching
- File search
- Web client / HTTP

**Agentic** — spins up a sub-loop to complete a goal:
- Web search (synthesized results)
- Skill search / skill runner

## Custom Tools

Custom tools are just decorated Python functions. Docstring becomes the description, type annotations become the schema. Pydantic models are supported for structured inputs.

```python
from nori import tool
from pydantic import BaseModel

@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return call_weather_api(city)

class SearchParams(BaseModel):
    query: str
    max_results: int = 10

@tool
def search(params: SearchParams) -> str:
    """Search the internal knowledge base."""
    ...

agent = Agent(tools=[Bash, get_weather, search])
```

Built-in and custom tools are treated identically — same list, same interface.

## Narration

Narration is a first-class framework feature, not a tool responsibility. At every tool boundary, the framework emits two separate events:

1. **Narration event** — the model's intent in natural language, emitted immediately before execution
2. **Tool call event** — the actual tool execution

```
on_narration("Reading the config file to find the model setting...")
on_tool_call(FileRead, path="config.json")

on_narration("Grepping the codebase for any other references...")
on_tool_call(Bash, command="grep -r 'grok-4-1' .")
```

The subscriber decides what to do with each event. A CLI prints the narration and shows a spinner. A Discord bot sends it as a message. A web UI streams it into a sidebar. Nori is output-agnostic.

The narrator prefix is configurable (`agent.narrator_prefix`). Narration can be disabled entirely by setting `narration=False`.

## Permissions

Agents accept either an allowlist or a denylist — never both. Declaring both is a runtime error. This is intentional: ambiguous permissions are a safety hazard, not a fallback case.

```python
# Only these tools are permitted
agent = Agent(tools=[Bash, WebSearch, Memory], allow=["bash", "web_search"])

# Everything except these
agent = Agent(tools=[Bash, WebSearch, Memory], deny=["bash"])

# Both → RuntimeError at startup
agent = Agent(tools=[...], allow=["bash"], deny=["web_search"])  # raises
```

Glob matching on tool names. Deny wins — but you can't have both.

## Context Management

Long-horizon coherence is a first-class concern. Agents on long tasks drift, repeat work, and lose the thread. Nori addresses this with a layered context management system:

**Scratchpad** — the agent writes free-form notes to itself mid-task. Reasoning, dead ends, decisions. Visible in the context, not returned to the user.

**TODO** — structured task tracking built in as a native tool. The agent adds and checks off items as it works. Keeps the goal visible across the full session.

**Running context summary** — after each turn, Nori maintains a rolling summary of what the agent has done, what it found, and where it is in the task. This summary is injected into the system prompt so it survives compaction and the agent never loses the thread.

**Autocompaction** — on by default. Triggered automatically before the context window fills. The running summary is the compaction anchor — you always compact into the summary, never into nothing.

**Result summarization** — large tool results (e.g. a 10k line grep) can be summarized before being appended to the conversation. The agent saw the full output; the context carries only the summary. Configured per-tool via the `@tool` decorator (API TBD).

```python
agent = Agent(
    ...
    running_context_summary=True,
)
```

## Self-Modification

Agents can be granted escalating levels of self-modification capability. These are opt-in and off by default. Each tier is a superset of the one below it.

**`self_custodian`** — stewardship of existing state, no new capabilities:
- `update_instructions()` — replace the system prompt
- `update_env(key, value)` — write to the env file
- `update_model()` — swap the model name in config
- Persistent memory/notes (read + write)

**`self_modify`** — extends capabilities through controlled meta-tools:
- Everything in `self_custodian`
- `register_tool(name, code, description)` — write, validate, and hot-register a new tool
- `deregister_tool(name)` — remove a tool by name
- New tools are sandboxed and go through Nori's validation layer before being attached

**`self_mutation`** — raw access, no leash:
- Everything in `self_modify`
- Direct file access to its own source and config via Bash/FilePatching
- No validation layer, no guardrails
- The user is explicitly taking responsibility

Both constructor kwargs and runtime methods are supported:

```python
# declarative
agent = Agent(
    ...,
    self_custodian=True,
    self_modify=True,
    self_mutation=False,
)

# runtime
agent.self_custodian = True
agent.self_modify = True
agent.self_mutation = True
```

The design principle: the agent operates *through* tools, not *around* them. Even self-modification is just another tool. `self_custodian` and `self_modify` enforce this — the leash is always the tool boundary. `self_mutation` removes the leash entirely; that's a conscious choice by the user, not a framework decision.

## Anti-Spin

For long-horizon or open-ended tasks, agents can thrash — retrying dead ends, searching blindly, making no real progress. Anti-spin detects this and terminates the loop before it wastes resources.

Anti-spin is opt-in and pairs with `max_turns=None`, which removes the turn ceiling and lets the agent run until it finishes or is stopped.

```python
from nori import CheckpointScrutiny

agent = Agent(
    ...,
    max_turns=None,
    checkpoint=20,
    checkpoint_scrutiny=CheckpointScrutiny.STRICT,
    checkpoint_compact=True,   # optional: replace turns with summary on pass
)
```

**How it works.** Every `checkpoint` turns, Nori fires two LLM calls on a separate, isolated context window — the main agent loop is paused:

1. **Summarize** — the last N turns are sent to the model with a compaction-style prompt. Returns a concise summary of what the agent has done, found, and attempted.

2. **Evaluate** — a fresh context window receives the summary and a scrutiny-tuned prompt: *"Is this agent making real progress toward its goal, or is it spinning?"* The model returns a binary judgment.

If the judgment is **spinning**: the loop raises `AntiSpinTerminated` and stops.

If the judgment is **progressing**: the loop continues. If `checkpoint_compact=True`, the N turns are replaced in the main context with the summary from step 1 — a free compaction as a side effect. If `checkpoint_compact=False`, the main context is untouched and the checkpoint was a pure health check.

**Scrutiny levels** control the evaluation prompt in call 2:

- `CheckpointScrutiny.STRICT` — demands concrete, measurable advancement. Not effort, not potential, not partial results. Clear evidence that the goal is within reach. Use for well-scoped tasks where progress is unambiguous: *"edit this file," "run these tests."*

- `CheckpointScrutiny.MODERATE` — expects a meaningful forward trajectory. Exploration and dead ends are acceptable as long as the agent is learning and narrowing. Use for broader tasks with some uncertainty: *"investigate this OS behavior."*

- `CheckpointScrutiny.LENIENT` — gives the agent the benefit of the doubt. Only terminates on obvious, undeniable spinning — repeating the same calls, zero new information across multiple turns. Use for hard, open-ended research tasks: *"debug this obscure SDK issue."*

**Design notes.**

- Both checkpoint calls use the same model as the agent. They are not logged to the main conversation history.
- `checkpoint` is a turn count, not a time interval. It fires at turn N, 2N, 3N, etc. since the loop started (not since the last checkpoint passed).
- `max_turns=None` and `checkpoint` are independent — you can use `checkpoint` with a finite `max_turns` as an early-exit heuristic, though the typical pairing is `max_turns=None + checkpoint`.
- If the agent finishes naturally before the checkpoint fires, anti-spin never runs.

## Other Features

- Visibility / audit / monitoring / logging out of the box
