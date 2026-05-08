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
    narrator_prefix="[::] ",
    running_context_summary=True,
)

agent.on_narration = lambda msg: print(msg)
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

Every built-in tool requires a `reason` parameter — the model's explanation for why it is calling the tool. This is not optional.

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

The `@tool` decorator automatically injects a required `reason: str` parameter into the tool's schema. The model must supply it; the underlying function never sees it. Built-in and custom tools are treated identically — same list, same interface, same `reason` requirement.

## Narration

Narration comes from two sources:

1. **Tool call `reason`** — every tool call carries a required `reason` field. The framework fires `on_narration(reason)` before executing each tool.

2. **Turn text content** — when the model produces text alongside tool calls in the same turn, that text is also narration. The framework fires `on_narration(text)` for it before the tool calls execute.

Text content in a turn with *no* tool calls is the final response, not narration — it is returned to the caller.

```python
agent.on_narration = lambda text: print(f"[::] {text}")
agent.on_tool_result = lambda name, result: log(name, result)
```

The default narration output is `tool_name[reason]`, printed to stdout:

```
bash[Reading the git log to find when this file last changed]
file_patch[Updating the retry logic in the request handler]
get_weather[User asked for the current weather in Austin]
```

Supplying a custom `on_narration` callback replaces the default entirely. The callback receives the already-formatted string — tool name is resolved via `inspect` and baked in before the callback fires:

```python
agent.on_narration = lambda narration: print(f"[::] {narration}")
```

A CLI prints narration and shows a spinner. A Discord bot sends it as a message. A web UI streams it into a sidebar. Nori is output-agnostic.

The narrator prefix is configurable (`narrator_prefix`). Narration can be disabled entirely with `narration=False`, which suppresses all narration output but does not remove `reason` from the tool schema — the model still supplies it.

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

**Autocompaction** — on by default and forced. At 70% context window fill, Nori injects a user-role message into the conversation:

> "You are at 70% full context window. You will auto compact at 85%, or you can choose to compact() sooner."

The agent can respond by calling the built-in `Compact` tool at a natural stopping point, or do nothing and let autocompaction trigger at 85%. Either path runs the same compaction logic. The running summary is the compaction anchor — you always compact into the summary, never into nothing.

**Result summarization** — on by default. Before a tool result is appended to the conversation, it goes through a separate summarization pass. The agent saw the full output; the context carries only the summary. The tool call's `reason` field is passed to the summarizer as the hint for what to keep and what to discard — the agent's stated intent drives the summarization. Opt out per-tool with `@tool(summarize_output=False)` for tools where the raw output must be preserved.

```python
agent = Agent(
    ...,
    autocompact=True,           # default
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

## Running the Agent

```python
response = await agent.run("Refactor the auth module to use the new token format")
print(response)
```

`agent.run()` is a coroutine. It starts the tool-calling loop, fires narration callbacks throughout, and returns the final response text when the loop terminates.

## Error Handling

Tool errors are returned to the model as tool results — not raised to the caller. The model sees the error text and decides what to do: retry with different arguments, try a different approach, or abandon the subtask. The existing `max_turns` ceiling is the natural backstop.

The caller only sees an exception if the framework itself fails (API error, `MaxTurnsExceeded`, `AntiSpinTerminated`).

## QoL Properties

Read-only properties on `Agent` for inspecting runtime state:

```python
agent.context_length    # total tokens in current conversation history
agent.token_counts      # dataclass: input, output, cached, total
agent.cost              # estimated cost in USD based on model pricing and token counts
agent.turn_count        # number of turns elapsed
agent.history           # raw list[dict] conversation history
agent.tool_calls        # all tool calls made so far, in order
agent.reset()           # clear history and turn count, keep config
```

`cost` is computed from a built-in `dict[str, ModelPricing]` keyed by model name. Prices are hardcoded and updated as models change.

## MCP Integration

MCP servers are first-class objects. Create one, name it, and pass it to any agent that needs it.

```python
from nori.mcp import MCPServer

filesystem = MCPServer(
    name="filesystem",
    command="npx @modelcontextprotocol/server-filesystem",
    args=["/tmp"],
)

github = MCPServer(
    name="github",
    url="https://api.example.com/mcp",
)

agent = Agent(
    ...,
    mcp_servers=[filesystem, github],
)
```

`command` + optional `args` and `env` declares a stdio server. `url` declares an HTTP/SSE server. Transport is explicit — no inference.

On registration, Nori connects to the server, discovers its tool schemas, and injects `reason` into each one. MCP tools appear in the agent's tool list identically to built-ins and custom tools — same interface, same `reason` requirement, same narration behavior.

**Runtime registration and deregistration** — pass the object, not a name:

```python
agent.add_mcp_server(filesystem)
agent.remove_mcp_server(filesystem)
```

`MCPServer` objects are shareable — the same instance can be registered with multiple agents.

**Curated servers** — Nori ships pre-built `MCPServer` factories for major use cases in `nori.mcp.servers`. These are not an exhaustive registry — just the ones that matter, done well:

```python
from nori.mcp.servers import GitHub, Filesystem, Postgres, SQLite, Slack, BraveSearch

agent = Agent(
    ...,
    mcp_servers=[
        GitHub(token="..."),
        Filesystem("/tmp"),
        Postgres(url="postgresql://..."),
    ]
)
```

Each factory returns a fully configured `MCPServer`. The user supplies only environment-specific values — tokens, paths, connection strings. Everything else is handled.

## Logging

All agent activity is written to a standard Python `logging` logger at `nori.agent`. Narration gets its own logger at `nori.narration`, making it easy to route to a separate file or handler:

```python
import logging
logging.getLogger("nori.narration").setLevel(logging.DEBUG)
```

No special configuration required — standard `logging` setup applies.
