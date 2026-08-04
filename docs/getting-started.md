# Getting Started

## Install

```bash
uv add nori-sdk
```

## Set up your environment

Nori uses the OpenAI message format and routes requests through any OpenAI-compatible provider. Set your API key for whichever provider you're using:

```bash
# xAI (recommended default)
export XAI_API_KEY=your_key_here

# OpenAI
export OPENAI_API_KEY=your_key_here

# Anthropic (via compatible proxy)
export ANTHROPIC_API_KEY=your_key_here
```

You can also use a `.env` file — Nori loads it automatically via `python-dotenv`.

### No API key? Use an installed CLI

If you have **Grok Build**, **Claude Code**, or **Codex** installed and logged in, Nori can use that connectivity instead of an API key. The CLI is **transport only** — text completion, **no tools of any kind** (vendor tools disabled; Nori tools are not registered and will raise if you pass them).

```python
# Grok Build on PATH (no XAI_API_KEY required) — text-only agent
nori.configure(model=Model(id="grok-4.5", provider=Provider.GROK_CLI))

# Claude Code on PATH
nori.configure(model=Model(id="claude-sonnet-4-6", provider=Provider.CLAUDE_CLI))

# Codex CLI on PATH
nori.configure(model=Model(id="gpt-5.4", provider=Provider.CODEX_CLI))
```

CLI:

```bash
nori --provider grok_cli --model grok-4.5 "Explain what this project does in one paragraph"
```

Subscription usage is billed by the vendor plan; `agent.cost` will report `$0` for CLI-backed runs. Agents that need tools require an HTTP provider and API key.

## Configure a model

Before creating agents, tell Nori which model to use:

```python
import nori
from nori import Model
from nori.providers import Provider

nori.configure(
    model=Model(id="grok-4.5", provider=Provider.XAI),
)
```

Any agent you create after this inherits the configured model. You can override it per-agent.

## Your first agent

```python
import asyncio
import nori
from nori import Agent, Model
from nori.providers import Provider
from nori.tools.bash import Bash

nori.configure(model=Model(id="grok-4.5", provider=Provider.XAI))

async def main():
    agent = Agent(
        name="MyAgent",
        system_prompt="You are a helpful assistant with shell access.",
        tools=[Bash],
    )
    agent.narration = True  # print what the agent is doing in real time

    result = await agent.run("What is today's date?")
    print(result)
    print(f"Turns: {agent.turn_count}  |  Cost: ${agent.cost:.4f}")

asyncio.run(main())
```

## Using built-in tools

Nori ships with tools for the most common agent tasks. Import and pass them to `tools=`:

```python
from nori.tools.bash import Bash
from nori.tools.file_read import FileRead
from nori.tools.file_write import FileWrite
from nori.tools.file_edit import FileEdit
from nori.tools.web_search import WebSearch

agent = Agent(
    name="ResearchAgent",
    system_prompt="You are a research assistant.",
    tools=[WebSearch, FileWrite],
)
```

See [Tools](tools.md) for the full list.

## Writing your own tools

Use the `@tool` decorator on any function:

```python
from nori.tool import tool

@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"Sunny, 22°C in {city}."

agent = Agent(
    name="WeatherAgent",
    system_prompt="Answer weather questions.",
    tools=[get_weather],
)
```

The decorator reads your function's name, docstring, and type annotations to build the schema automatically. See [Tools](tools.md) for more.

## Next steps

- [The Agent](agent.md) — all constructor options and runtime controls
- [Tools](tools.md) — built-in tools, `@tool`, bound tools
- [Demos](demos.md) — full end-to-end examples
