"""
Browser demo 3: Google Search results via BrowserAgent.

Google's DOM is heavily obfuscated — no readable labels, everything is
div.VwiC3b and span.LC20lb. This is the case where the LLM will likely
request element screenshots to identify what it's looking at.

Run with: uv run python demos/browser3_demo.py
"""

import asyncio

import config  # noqa: F401 — triggers nori.configure() with grok-4.3

from nori import Agent
from nori.tools.browser import BrowserAgent

TASK = """\
Search Google for: Playwright Python async best practices

Return the top 3 organic results (not ads):
  - Title
  - URL
  - One sentence on what the result covers
"""

async def main():
    agent = Agent(
        name="GoogleSearchAgent",
        system_prompt="You are a web research assistant. Use BrowserAgent to complete tasks that require browser interaction.",
        tools=[BrowserAgent],
        max_turns=4,
    )
    agent.narration = True

    print("=" * 60)
    print("Demo 3 — Google Search results [BrowserAgent]")
    print("=" * 60)
    print()

    result = await agent.run(TASK)

    print()
    print(result)
    print()
    print(f"Turns: {agent.turn_count}  |  Tool calls: {len(agent.tool_calls)}  |  Cost: ${agent.cost:.4f}")

asyncio.run(main())
