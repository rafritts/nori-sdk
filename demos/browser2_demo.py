"""
Browser demo 2: Wikipedia article walk via WebClient.

Fetches Alan Turing's article, picks a linked article from the opening
paragraphs, fetches that too, and returns a summary. Two hops, plain HTML,
no Playwright needed.

Run with: uv run python demos/browser2_demo.py
"""

import asyncio

import config  # noqa: F401 — triggers nori.configure() with grok-4.3

from nori import Agent
from nori.tools.web_client import WebClient

TASK = """\
Use WebClient to fetch the Wikipedia article on Alan Turing:
  https://en.wikipedia.org/wiki/Alan_Turing

Find the first article linked in the main body text (not the infobox or nav).
Fetch that linked article with WebClient.

Return:
  - Which article you jumped to and why you chose it
  - A two-paragraph summary of that second article
"""

async def main():
    agent = Agent(
        name="WikiWalker",
        system_prompt="You are a research assistant. Fetch pages with WebClient and synthesize clear answers.",
        tools=[WebClient],
        max_turns=6,
    )
    agent.narration = True

    print("=" * 60)
    print("Demo 2 — Wikipedia article walk [WebClient]")
    print("=" * 60)
    print()

    result = await agent.run(TASK)

    print()
    print(result)
    print()
    print(f"Turns: {agent.turn_count}  |  Tool calls: {len(agent.tool_calls)}  |  Cost: ${agent.cost:.4f}")

asyncio.run(main())
