"""
Demonstrates Nori's context management features.

Long-running agents accumulate history. Nori handles this in two ways:

  running_context_summary — after each final response, the history is
    compressed into a rolling summary so the next turn stays lean.

  Autocompaction — when context fill hits 70%, a warning is injected;
    at 85%, the history is compacted automatically mid-run.

Shows:
  1. Running context summary across a multi-turn conversation
  2. Forced autocompaction by setting a very small max_context_chars
"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio

from nori import Agent, Model
from nori.audit import AuditLogger
from nori.tool import tool

DIVIDER = "=" * 60


def section(title: str) -> None:
    print(f"\n{DIVIDER}")
    print(title)
    print(DIVIDER)


@tool
def get_chapter(number: int) -> str:
    """Return the text of a book chapter by number."""
    chapters = {
        1: "Chapter 1: The sun rose over the quiet valley. Birds sang. The river ran clear.",
        2: "Chapter 2: A stranger arrived at dusk, carrying nothing but a worn leather satchel.",
        3: "Chapter 3: The village elders convened. Something had to be done about the northern threat.",
        4: "Chapter 4: By morning, the stranger was gone. Only a letter remained on the table.",
        5: "Chapter 5: The letter revealed a secret buried for thirty years beneath the old mill.",
    }
    return chapters.get(number, f"Chapter {number} not found.")


# ── Scenario 1: Running context summary ──────────────────────────────────────

async def scenario_running_summary(auditor: AuditLogger):
    section("SCENARIO 1 — Running context summary across multiple turns")

    agent = Agent(
        name="BookAgent",
        model=Model(id="grok-4.3"),
        system_prompt="You are a literary assistant helping a reader track a story.",
        tools=[get_chapter],
    )
    agent.running_context_summary = True
    agent.narration = True
    agent.auditor = auditor

    print("Turn 1:")
    r1 = await agent.run("Fetch chapter 1 and tell me what it's about.")
    print(f"  Agent: {r1}")
    print(f"  History length: {len(agent.history)} messages")

    print("\nTurn 2:")
    r2 = await agent.run("Now fetch chapter 2. How does it connect to chapter 1?")
    print(f"  Agent: {r2}")
    print(f"  History length: {len(agent.history)} messages")

    print("\nTurn 3:")
    r3 = await agent.run("Fetch chapters 3, 4, and 5. Give me a full story summary.")
    print(f"  Agent: {r3}")
    print(f"  History length: {len(agent.history)} messages")
    print(f"\n  Running summary:\n  {agent._running_summary[:300]}...")


# ── Scenario 2: Autocompaction ────────────────────────────────────────────────

async def scenario_autocompaction(auditor: AuditLogger):
    section("SCENARIO 2 — Autocompaction triggered by context fill")

    agent = Agent(
        name="CompactAgent",
        model=Model(id="grok-4.3"),
        system_prompt="You are a data agent. Fetch chapters as requested.",
        tools=[get_chapter],
        max_turns=20,
    )
    agent.narration = True
    agent.auditor = auditor
    # Set a very small context window to force compaction quickly
    agent.max_context_chars = 2_000

    print(f"max_context_chars: {agent.max_context_chars:,}")
    print(f"Context fill before run: {agent._context_fill():.0%}\n")

    result = await agent.run(
        "Fetch all 5 chapters one by one and give me a running commentary on the story as it unfolds."
    )

    print(f"Agent: {result}")
    print(f"\nContext fill after run: {agent._context_fill():.0%}")
    print(f"Turns: {agent.turn_count}  |  Tool calls: {len(agent.tool_calls)}")


async def main():
    print("Nori context management demo")
    auditor = AuditLogger("logs/context_demo.audit.log")
    await scenario_running_summary(auditor)
    await scenario_autocompaction(auditor)
    auditor.close()
    print(f"\n{DIVIDER}\nDone.\n{DIVIDER}")


asyncio.run(main())
