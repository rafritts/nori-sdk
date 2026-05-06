# Overview

Nori is the "Spring Boot" of agentic frameworks — opinionated defaults that work in production, with escape hatches when you need to override them. The name comes from the seaweed that holds sushi together: the framework that holds the model, tools, loop, narration, and output surface into one coherent thing.

Most agentic frameworks (LangChain, LlamaIndex, OpenAI Agents SDK, CrewAI) give you plumbing but no tools. You end up rebuilding bash, file patching, and web search yourself, independently, every time. Nori ships all of it.

## Interface

The API should feel familiar to anyone who has used an existing agentic framework:

```python
from nori.tools import Bash, FilePatching, WebSearch, Memory

agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant",
    tools=[Bash, FilePatching, WebSearch, Memory],
    narration=True,
    autocompact=True,
)

agent.set_narrator_prefix("[::] ")
agent.subscribe_narration(lambda msg: print(msg))
agent.use_running_context_summary(True)
```

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

The narrator prefix is configurable (`set_narrator_prefix`). Narration can be disabled entirely by setting `narration=False`.

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

**`exclude_from_main_context()`** — large tool results (e.g. a 10k line grep) are summarized and the raw output is dropped. The agent saw it; the context doesn't carry it forever.

```python
agent = Agent(
    ...
    autocompact=True,   # default
)

agent.use_running_context_summary(True)
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
agent.allow_self_custodian(True)
agent.allow_self_modify(True)
agent.allow_self_mutation(True)
```

The design principle: the agent operates *through* tools, not *around* them. Even self-modification is just another tool. `self_custodian` and `self_modify` enforce this — the leash is always the tool boundary. `self_mutation` removes the leash entirely; that's a conscious choice by the user, not a framework decision.

## Other Features

- Visibility / audit / monitoring / logging out of the box
