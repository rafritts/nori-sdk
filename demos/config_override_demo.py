"""
Config override demo: shows how to import the shared config and override
specific fields for individual agents.

Imports config (which sets grok-4.3 as the default model and max_turns=10),
then constructs three agents:
  1. Default agent       — uses everything from config, no overrides
  2. Fast agent          — overrides model to grok-4-1-fast-reasoning
  3. Deep-dive agent     — overrides max_turns only, keeps the default model

All three run the same task so the behaviour differences are visible.
"""

import asyncio

import nori
from nori import Agent, Model, Provider
from nori.tools.bash import Bash

TASK = "What is today's date? Use the shell to find out, then reply with just the date."

DIVIDER = "=" * 60


async def run(label: str, agent: Agent) -> None:
    print(f"\n{DIVIDER}")
    print(f"{label}  (model={agent.model}, max_turns={agent._max_turns})")
    print(DIVIDER)
    result = await agent.run(TASK)
    print(f"→ {result}")
    print(f"  Turns: {agent.turn_count}  |  Cost: ${agent.cost:.4f}")


async def main() -> None:
    # 1. Uses global defaults — no kwargs needed beyond name and tools.
    default_agent = Agent(name="DefaultAgent", tools=[Bash])
    default_agent.narration = True

    # 2. Overrides model; everything else (max_turns, timeouts) from config.
    fast_agent = Agent(
        name="FastAgent",
        model=Model(id="grok-4-1-fast-reasoning", provider=Provider.XAI),
        tools=[Bash],
    )
    fast_agent.narration = True

    # 3. Overrides max_turns only; inherits model from config.
    deep_agent = Agent(name="DeepAgent", tools=[Bash], max_turns=3)
    deep_agent.narration = True

    print(DIVIDER)
    print("Config override demo")
    print(f"Global default model: {nori.config.get_defaults().model.id}")
    print(DIVIDER)

    await run("1. Default agent (no overrides)", default_agent)
    await run("2. Fast agent   (model overridden)", fast_agent)
    await run("3. Deep agent   (max_turns overridden)", deep_agent)

    print(f"\n{DIVIDER}")


asyncio.run(main())
