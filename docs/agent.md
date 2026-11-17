# The Agent

`Agent` is the core construct. It owns a tool-calling loop: send a message, get a response, execute any tool calls, repeat until the model stops calling tools or a limit is hit.

```python
import nori
from nori import Agent, Model
from nori.providers import Provider
from nori.tools.bash import Bash

nori.configure(model=Model(id="grok-4.5", provider=Provider.XAI))

agent = Agent(
    name="MyAgent",
    system_prompt="You are a helpful assistant.",
    tools=[Bash],
    max_turns=20,
)

result = await agent.run("What files are in /tmp?")
```

A model is required — pass `model=` or call `nori.configure(model=...)` first.

---

## User-facing text during tool use

While tools are running, free-form assistant `content` is **not** treated as the final answer. Instead:

1. Each tool schema includes an optional **`update_for_user`** string (one sentence). When present, it is delivered via `on_assistant_content` as that tool starts.
2. When the model stops calling tools after at least one tool ran, Nori injects a system turn (*“Provide the user with a final output”*) and completes once more with `tool_choice="none"`. That reply is the user-facing final answer.

Runs that never call tools behave as before: the no-tool assistant message is the final reply.

---

## Constructor parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | required | Name used in logs and narration |
| `system_prompt` | `str` | `""` | The agent's system prompt |
| `model` | `Model` | from config | Model to use; falls back to `nori.configure()` |
| `tools` | `list` | `[]` | Tools available in every turn |
| `mcp_servers` | `list[MCPServer]` | `[]` | MCP servers connected for the duration of each run |
| `deferred_tools` | `list \| dict` | `None` | Tools loaded lazily (see below) |
| `show_tool_stubs` | `bool` | `False` | Show deferred tool stubs in the schema |
| `max_turns` | `int \| None` | from config, else `10` | Turn limit; `None` removes the ceiling |
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
| `output_format` | `OutputFormat` | `TEXT` | Return type of `run()`: plain text or OpenAI message shapes |
| `tool_args_filter` | `callable` | `None` | Rewrite tool args at invoke time `(name, args) → args` |
| `tool_schema_filter` | `callable` | `None` | Mutate tool schemas before the model sees them |
| `require_no_tools_ack` | `bool` | `False` | Require `NO_TOOL_CALLS` (or a tool call) before ending a no-tool turn |
| `no_tools_ack_max` | `int` | `3` | Max no-tools challenge retries |
| `no_tools_ack_message` | `str \| None` | `None` | Override the no-tools challenge text |
| `force_tool` | `str \| None` | `None` | Force `tool_choice` to this function until any tool runs |

CLI connectivity providers (`Provider.GROK_CLI`, `CLAUDE_CLI`, `CODEX_CLI`) reject agents that pass tools, deferred tools, MCP servers, scratchpad, self-modify, or `force_tool`.

---

## Global config

Set defaults once and all agents inherit them:

```python
import nori
from nori import Model
from nori.providers import Provider

nori.configure(
    model=Model(id="grok-4.5", provider=Provider.XAI),
    max_turns=15,
    tool_timeout=30.0,
    run_timeout=120.0,
)
```

Other `configure()` options: `tool_models` (per-tool model overrides), `server` (HITL server: `True` or a dict with `host`/`port`/`token`), `durable` (crash journal: `True` by default, `False` to disable, or a path / `{"path": "..."}`), `notify` (Slack/webhook defaults for `Notify`), `control_tower` + `project` (remote audit stream).

Override any default per-agent by passing the parameter directly to `Agent(...)`. See [`config_override_demo.py`](https://github.com/rafritts/nori-sdk/blob/master/demos/config_override_demo.py) for a full example.

---

## Running the agent

```python
result = await agent.run("Your task here")
```

`run()` returns the agent's final text response as a string by default (`OutputFormat.TEXT`). After the run:

```python
agent.turn_count      # how many turns were used
agent.tool_calls      # list of all tool call records
agent.cost            # total cost in USD (provider ticks when available)
agent.token_counts    # {prompt, completion, reasoning, cached, total}
agent.elapsed         # seconds for the last run, or None
agent.trace_id        # B3 trace ID for this run
agent.history         # full message history
agent.run_id          # journal id for this run, or None if durability is off
```

### Durable runs

Runs are journaled by default to `~/.nori/runs.db` (`$NORI_STATE_PATH` overrides the path). The journal commits before each model call and around each tool call, using SQLite WAL with `synchronous=FULL`. Killing the process loses only the step that had not committed.

```python
result = await agent.run("Purge the old logs.")   # logs: run started id=<run_id>
# process dies

result = await agent.run(run_id="<run_id>")       # same agent construction, continues
```

`nori.list_runs()` lists journaled runs (`status` is `running`, `waiting`, `done`, or `error`). `nori.configure(durable=False)` turns the journal off. `nori.configure(durable="/path/to.db")` sets the file.

Rebuild the agent with the same tools, scratchpad schema, and MCP servers before resuming. History, system prompt, model id, max turns, scratchpad contents, and which deferred tools were expanded are restored from the journal.

A tool whose result was committed is not run again. A tool that had started but not committed runs again, so side-effecting tools can run twice. Nested agent calls from a tool resume under a stable child id instead of starting over.

A run that already finished returns its stored result. A run that ended with an exception (including max turns and anti-spin) raises again and does not retry. `run_timeout` does not close the run; resume continues it, and the timeout clock starts over.

The journal contains the full transcript. Keep the file private.

### Images

Pass vision inputs via `images=`:

```python
from nori import Image

result = await agent.run(
    "Describe this screenshot.",
    images=[Image(path="shot.png")],
)
```

`Image` accepts exactly one of `path`, `url`, or `data`. Optional: `detail`, `resize`, `output_format`, `remove_from_context_after_read`.

### Reset

```python
agent.reset()  # clear history, counters, and run state
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

`deferred_tools` can also be a dict of named groups for batch expand.

---

## Runtime callbacks

```python
agent.narration = True                        # print tool calls as they happen
agent.on_narration = lambda msg: log(msg)     # custom narration handler
agent.narrator_prefix = "[agent1] "           # prefix for multi-agent disambiguation
agent.on_assistant_content = lambda text: ... # mid-run user-facing status / final prose
agent.on_tool_result = lambda name, result, call_id, trace_id: ...
```

Narration knobs: `narration_call_id` (default `True`), `narration_trace_id` (default `False`), `narration_summary` (default `True`).

Optional run-time attributes: `conversation_id` (sticky id for provider prompt-cache routing), `dynamic_context` (appended after each user prompt so the system message stays a stable cache prefix).

See [Observability](observability.md) for full details.
