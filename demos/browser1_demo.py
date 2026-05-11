"""
Browser demo 1: Hacker News top stories via WebClient.

Plain HTML — no JS, no Playwright, no LLM loop inside the tool.
Fast and cheap.

Run with: uv run python demos/browser1_demo.py
"""

import asyncio

import config  # noqa: F401 — triggers nori.configure() with grok-4.3

from nori import Agent
from nori.tools.web_client import WebClient

TASK = """\
Use WebClient to fetch https://news.ycombinator.com.
Return the top 10 stories as a numbered list: title, score, and comment count.
"""

async def main():
    agent = Agent(
        name="HNAgent",
        system_prompt="You are a research assistant. Fetch pages with WebClient and extract the requested information.",
        tools=[WebClient],
        max_turns=4,
    )
    agent.narration = True

    print("=" * 60)
    print("Demo 1 — Hacker News top stories [WebClient]")
    print("=" * 60)
    print()

    result = await agent.run(TASK)

    print()
    print(result)
    print()
    print(f"Turns: {agent.turn_count}  |  Tool calls: {len(agent.tool_calls)}  |  Cost: ${agent.cost:.4f}")

asyncio.run(main())
