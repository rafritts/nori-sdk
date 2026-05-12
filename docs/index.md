# Nori

**A batteries-included agent framework for Python.**

Most agent frameworks give you plumbing. You still have to wire up tools, handle context limits, guard against infinite loops, hook in observability, and figure out permissions — before your agent does anything useful.

Nori ships with all of that solved. You bring the task.

It's not clever. It's not trying to be elegant. It's a clean tool-calling loop with the production concerns already handled: a full built-in tool library, permissions, observability, anti-spin protection, MCP support, and a context management system that keeps long-running agents from blowing up.

If you've spent a week getting an agent to do real work in a real application, Nori is what you were trying to build.

---

## Install

```bash
uv add nori-sdk
```

For optional integrations:

```bash
uv add "nori-sdk[browser]"    # Playwright-based browser tools
uv add "nori-sdk[postgres]"   # Postgres tools
uv add "nori-sdk[redis]"      # Redis tools
uv add "nori-sdk[mongo]"      # MongoDB tools
uv add "nori-sdk[all]"        # Everything
```

---

## A minimal agent

```python
import asyncio
from nori import Agent
from nori.tools.bash import Bash

async def main():
    agent = Agent(
        name="MyAgent",
        system_prompt="You are a helpful assistant with shell access.",
        tools=[Bash],
    )
    result = await agent.run("What OS am I on?")
    print(result)

asyncio.run(main())
```

That's it. No boilerplate, no configuration required. The agent runs, calls `Bash` if it needs to, and returns a string.

---

## What's included

| Concern | What Nori provides |
|---|---|
| Tools | 20+ built-in tools across files, shell, web, git, databases, and more |
| Context management | Autocompaction at 85% fill, running summaries, manual `Compact` tool |
| Anti-spin | Checkpoint-based loop detection with configurable scrutiny |
| Permissions | Allow-list or deny-list with glob support |
| Observability | Narration, structured audit log with B3 tracing, cost tracking |
| MCP | First-class `MCPServer` with curated factories |
| Orchestration | Agents are tools — pass one agent as a tool to another |
| CLI | Quick-fire agents from the terminal for prototyping |

---

[Get started →](getting-started.md)
