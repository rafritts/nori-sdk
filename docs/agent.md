# The Agent

`Agent` is the core construct. It owns a tool-calling loop: send a message, get a response, execute any tool calls, repeat until the model stops calling tools or a limit is hit.

```python
from nori import Agent
from nori.tools.bash import Bash

agent = Agent(
    name="MyAgent",
    system_prompt="You are a helpful assistant.",
    tools=[Bash],
    max_turns=20,
)

result = await agent.run("What files are in /tmp?")
```

---

## Constructor parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | required | Name used in logs and narration |
| `system_prompt` | `str` | `""` | The agent's system prompt |
| `model` | `Model` | from config | Model to use; falls back to `nori.configure()` |
| `tools` | `list` | `[]` | Tools available in every turn |
| `deferred_tools` | `list \| dict` | `None` | Tools loaded lazily (see below) |
| `show_tool_stubs` | `bool` | `False` | Show deferred tool stubs in the schema |
| `max_turns` | `int \| None` | from config | Turn limit; `None` removes the ceiling |
| `description` | `str` | `""` | Used when the agent is passed as a tool |
| `context_files` | `list[ContextFile]` | `None` | Files injected into conversation at start |
| `permissions` | `Permissions` | `None` | Allow or deny specific tools |
| `checkpoint` | `Checkpoint` | `None` | Anti-spin configuration |
| `self_modify` | `SelfModify` | `None` | Self-modification tier |
| `summarize_tool_output` | `bool` | `False` | Summarize all tool outputs by default |
| `running_context_summary` | `bool` | `False` | Compress history after each turn |
| `tool_timeout` | `float \| None` | from config | Per-tool call timeout in seconds |
| `run_timeout` | `float \| None` | from config | Total run timeout in seconds |
| `scratchpad` | `Scratchpad` | `None` | Shared scratchpad for multi-agent state |

---

## Global config

Set defaults once and all agents inherit them:

```python
import nori
from nori import Model
from nori.providers import Provider

nori.configure(
    model=Model(id="grok-4", provider=Provider.XAI),
    max_turns=15,
    tool_timeout=30.0,
    run_timeout=120.0,
)
```

Override any default per-agent by passing the parameter directly to `Agent(...)`. See [`config_override_demo.py`](https://github.com/rafritts/nori/blob/master/demos/config_override_demo.py) for a full example.

---

## Running the agent

```python
result = await agent.run("Your task here")
```

`run()` returns the agent's final text response as a string. After the run:

```python
agent.turn_count   # how many turns were used
agent.tool_calls   # list of all tool call records
agent.cost         # total cost in USD
agent.trace_id     # B3 trace ID for this run
agent.history      # full message history
```

---

## Multi-turn conversations

Call `run()` multiple times on the same agent to continue the conversation:

```python
r1 = await agent.run("Fetch chapter 1.")
r2 = await agent.run("Now fetch chapter 2. How does it connect?")
```

History accumulates across calls. Use `running_context_summary=True` to keep it lean over many turns — after each call, the history is compressed into a rolling summary.

---

## Context files

Inject file contents into the conversation at startup using `ContextFile`. Useful for giving the agent reference material, a schema, or a codebase overview without including it in every message.

```python
from nori.context import ContextFile
from nori.enums import ContextRole

agent = Agent(
    name="SchemaAgent",
    system_prompt="You answer questions about our database schema.",
    context_files=[
        ContextFile(path="schema.sql", role=ContextRole.SYSTEM),
    ],
)
```

`ContextRole` options: `SYSTEM`, `USER`, `ASSISTANT`.

---

## Deferred tools

Tools can be held back from the initial schema and loaded lazily. This keeps the schema small for models with token-sensitive tool lists.

```python
from nori.tools.web_search import WebSearch
from nori.tools.bash import Bash

agent = Agent(
    name="MyAgent",
    tools=[Bash],
    deferred_tools=[WebSearch],
    show_tool_stubs=True,  # model sees stub descriptions but not full schemas
)
```

---

## Runtime callbacks

```python
agent.narration = True                        # print tool calls as they happen
agent.on_narration = lambda msg: log(msg)     # custom handler
agent.narrator_prefix = "[agent1] "           # prefix for multi-agent disambiguation
agent.on_tool_result = lambda name, result, call_id, trace_id: ...
```

See [Observability](observability.md) for full details.
