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
)

agent.set_narrator_prefix("[::] ")
agent.subscribe_narration(lambda msg: print(msg))
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

## Other Features

- Easy allowlist/denylist configuration
- Visibility / audit / monitoring / logging out of the box
