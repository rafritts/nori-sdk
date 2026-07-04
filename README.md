# Nori

**A batteries-included agent framework for Python applications.**

On the command line, agents are already great — Claude Code and Codex are killers. Inside *your application*, the story is different: every framework hands you a graph DSL, five hundred integrations, and a shrug. The hard parts — context management, loop safety, permissions, observability, tools that actually work — are left as an exercise for the reader.

Nori is the hard parts, as a library. You bring the task.

```python
import asyncio
import nori
from nori import Agent, Model
from nori.providers import Provider
from nori.tools.bash import Bash

nori.configure(model=Model(id="grok-4", provider=Provider.XAI))

agent = Agent(
    name="Ops",
    system_prompt="You are an assistant with shell access.",
    tools=[Bash],
)

print(asyncio.run(agent.run("How much disk space is free?")))
```

That's a complete agent. It already has autocompaction, cost tracking, structured audit logging with trace propagation, timeouts, and a turn ceiling. None of that is visible in the code — that's the point.

## Install

```bash
uv add nori-sdk
```

```bash
uv add "nori-sdk[browser]"   # Playwright browser tools
uv add "nori-sdk[postgres]"  # Postgres tools
uv add "nori-sdk[redis]"     # Redis tools
uv add "nori-sdk[mongo]"     # MongoDB tools
uv add "nori-sdk[all]"       # everything
```

Works with any OpenAI-compatible endpoint: xAI, OpenAI, Anthropic (via proxy), Bedrock, Ollama, whatever you're running.

## Tools you don't have to write

Files, shell, web, git, databases, CSV/JSON, browser — 20+ built-ins, many in two flavors: a **native** version (one call, raw result) and an **agentic** version (spins up its own sacrificial context window, does multi-step work, returns a summary — your main context never sees the mess).

```python
from nori.tools.bash import Bash            # run a command
from nori.tools.bash_agent import BashAgent # accomplish a goal via many commands
from nori.tools.web_search import WebSearch
from nori.tools.file_edit import FileEdit
from nori.tools.git import Git
```

*Run it:* [file CRUD](demos/file_crud_demo.py) · [git workflow](demos/git_demo.py) · [JSON/CSV](demos/json_csv_demo.py) · [browser scraping](demos/browser1_demo.py)

Your own tools are one decorator:

```python
from nori.tool import tool

@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return weather_api(city)

agent = Agent(name="Concierge", system_prompt="...", tools=[get_weather, WebSearch])
```

Name, docstring, and type hints become the schema. Done. *Run it:* [tool_decorator_demo.py](demos/tool_decorator_demo.py)

## Agents are tools

Any `Agent` can be passed into another agent's `tools=` list. The orchestrator sees a tool; the sub-agent runs its full loop in an isolated context and returns a summary. Traces propagate across the whole tree.

```python
researcher = Agent(
    name="Researcher",
    description="Looks up and verifies facts.",
    system_prompt="You are a research specialist.",
    tools=[WebSearch],
)

writer = Agent(
    name="Writer",
    description="Turns notes into clean prose.",
    system_prompt="You are a technical writer.",
)

orchestrator = Agent(
    name="Editor",
    system_prompt="Coordinate the researcher and writer to answer the user.",
    tools=[researcher, writer],
)

result = await orchestrator.run("Compare Python's asyncio to Go's goroutines.")
```

Need scale instead of hierarchy? Fan out and chain:

```python
# same agent, 50 inputs, 5 at a time
results = await nori.map(triage, tickets, concurrency=5)

# stage 2 starts as soon as stage 1 emits its first result
results = await nori.pipeline([classifier, summarizer], documents)
```

*Run it:* [agent_as_tool_demo.py](demos/agent_as_tool_demo.py) — researcher and writer under an orchestrator · [parallel_demo.py](demos/parallel_demo.py) — three specialist code reviewers dispatched in a single turn, traces propagating across all four agents

## Agents that don't wander off

Long-running agents drift, loop, and thrash. Nori watches for it:

```python
from nori import Agent, Checkpoint, CheckpointScrutiny, Permissions

agent = Agent(
    name="Digger",
    system_prompt="...",
    tools=[Bash, WebSearch],
    max_turns=None,                       # no ceiling — checkpoint is the guardrail
    checkpoint=Checkpoint(every=5, scrutiny=CheckpointScrutiny.MODERATE),
    permissions=Permissions(deny=["Bash"]),   # glob patterns, allow- or deny-list
    tool_timeout=30,
    run_timeout=600,
)
```

Every 5 turns, an isolated evaluator reads the recent history and answers one question: *is this agent making progress, or spinning?* Spinning raises `AntiSpinTerminated` instead of burning your budget. Context is managed the same way — a warning lands in the conversation at 70% full, autocompaction into a running summary fires at 85%. You configure nothing.

*Run it:* [anti_spin_demo.py](demos/anti_spin_demo.py) · [permissions_demo.py](demos/permissions_demo.py) · [context_demo.py](demos/context_demo.py)

## Watch it work

Every tool call carries a required `reason` — so narration is free, and it goes wherever your app needs it:

```python
agent.narration = True
agent.on_narration = lambda msg: websocket.send(msg)   # or print, or Discord, or a sidebar
```

```
Ops → Bash[Checking disk usage on the root volume]
Ops → Bash[1.24s]
Ops: 3 turns | 2,410 tokens | $0.0061 | 4.2s
```

Cost, tokens, turns, and the full tool-call log are properties on the agent. A structured audit trail with B3 trace/span IDs is emitted for every run — pipe it to whatever observability stack you already have.

*Run it:* [narration_demo.py](demos/narration_demo.py) · [observability_demo.py](demos/observability_demo.py) — Python logging vs. the audit stream, side by side

## Ship it

Your agent is an OpenAI-compatible API in three lines. Point Open WebUI, or any OpenAI client, at it:

```python
from nori import Agent, serve

def make_agent():
    return Agent(name="Support", system_prompt="...", tools=[...])

serve(make_agent, port=7732)   # POST http://localhost:7732/v1/chat/completions
```

Need a human in the loop? Give the agent the `HumanInput` tool and it will pause mid-run, post a question to the embedded server, and wait for your app to answer over HTTP.

*Run it:* [chatbot_demo.py](demos/chatbot_demo.py) — point Open WebUI at your agent · [hitl_demo.py](demos/hitl_demo.py) — approval flow with a simulated human

## MCP

MCP servers are first-class. Declare one, pass it to an agent, and its tools show up like natives — same `reason` requirement, same narration, same permissions.

```python
from nori.mcp import MCPServer
from nori.mcp.servers import Filesystem, GitHub, Postgres

agent = Agent(
    name="RepoBot",
    system_prompt="...",
    mcp_servers=[Filesystem("/tmp"), GitHub(token="...")],
)
```

## Demos, not promises

Every feature above has a runnable end-to-end demo in [`demos/`](demos/) — not snippets, full working programs. Two worth starting with:

- **[retail_demo.py](demos/retail_demo.py)** — a complete RMA pipeline: two agents collaborating across a Redis message queue backed by Postgres, processing product returns end to end.
- **[hard_demo.py](demos/hard_demo.py)** — broken repo recovery: an agent drops into a Python project with three planted bugs and works it back to green.

## And the rest

| Concern | What you get | See it run |
|---|---|---|
| Context | Autocompaction, running summaries, scratchpads, context files, tool-output summarization | [context_demo.py](demos/context_demo.py) |
| Safety | Anti-spin checkpoints, permissions, tool/run timeouts, `max_turns` | [anti_spin_demo.py](demos/anti_spin_demo.py) |
| Observability | Narration callbacks, audit log with B3 tracing, cost & token accounting | [observability_demo.py](demos/observability_demo.py) |
| Orchestration | Agents as tools, `nori.map`, `nori.pipeline`, parallel tool dispatch | [parallel_demo.py](demos/parallel_demo.py) |
| Vision | Pass images to `agent.run()`, with automatic context stripping after read | [vision_demo.py](demos/vision_demo.py) |
| Self-modification | Opt-in tiers: rewrite its own prompt → manage its own tools → change its own model | [self_modify_demo.py](demos/self_modify_demo.py) |
| Notifications | `Notify` tool — the agent signals success/failure to your app | [notify_demo.py](demos/notify_demo.py) |
| Databases | Postgres, Redis, Mongo tools with demos for each | [postgres](demos/postgres_demo/) · [redis](demos/redis_demo/) · [mongo](demos/mongo_demo/) |
| Deferred tools | Register many tools, expose stubs, let the model load them on demand | — |
| CLI | `nori` command for quick-fire agents from the terminal | — |

**[Get started →](docs/getting-started.md)** · [Agent API](docs/agent.md) · [Tools](docs/tools.md) · [Patterns](docs/patterns.md) · [Anti-spin](docs/anti-spin.md) · [MCP](docs/mcp.md) · [Observability](docs/observability.md) · [Demos](docs/demos.md)

MIT licensed. Python 3.13+.
