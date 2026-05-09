"""
Demonstrates Nori's anti-spin checkpoint system.

Anti-spin evaluates the agent's recent history every N turns and raises
AntiSpinTerminated if it detects the agent is looping without progress.

Shows:
  1. A healthy agent completing a multi-step task (no spin detected)
  2. An agent that gets stuck in a loop — anti-spin fires and halts it
"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio

from nori import Agent
from nori.anti_spin import CheckpointScrutiny
from nori.exceptions import AntiSpinTerminated
from nori.tool import tool

DIVIDER = "=" * 60


def section(title: str) -> None:
    print(f"\n{DIVIDER}")
    print(title)
    print(DIVIDER)


# ── Scenario 1: healthy agent ─────────────────────────────────────────────────

@tool
def fetch_record(record_id: str) -> str:
    """Fetch a record by ID."""
    records = {
        "A1": "Name: Alice, Status: Active",
        "B2": "Name: Bob, Status: Inactive",
        "C3": "Name: Carol, Status: Active",
    }
    return records.get(record_id, "Not found.")


@tool
def summarize_records(records: str) -> str:
    """Summarize a list of records into a brief report."""
    return f"Summary complete. Input: {records[:80]}"


async def scenario_healthy():
    section("SCENARIO 1 — Healthy agent (checkpoint passes)")

    agent = Agent(
        name="RecordAgent",
        system_prompt="You are a data agent. Fetch and summarize records efficiently.",
        tools=[fetch_record, summarize_records],
        checkpoint=3,
        checkpoint_scrutiny=CheckpointScrutiny.MODERATE,
    )
    agent.summarize_tool_output = False
    agent.narration = True

    result = await agent.run("Fetch records A1, B2, and C3, then summarize them.")
    print(f"\nAgent: {result}")
    print(f"Turns: {agent.turn_count}  |  Anti-spin: not triggered")


# ── Scenario 2: spinning agent ────────────────────────────────────────────────

_call_count = 0

@tool
def investigate(target: str) -> str:
    """Investigate a target. Always returns ambiguous results."""
    global _call_count
    _call_count += 1
    return (
        f"[Attempt {_call_count}] Target '{target}' shows anomalous readings. "
        "Results are inconclusive. Further investigation required."
    )


async def scenario_spin():
    section("SCENARIO 2 — Spinning agent (AntiSpinTerminated raised)")

    agent = Agent(
        name="SpinAgent",
        system_prompt=(
            "You are a diagnostic agent. You must keep investigating until you reach "
            "a definitive conclusion. Do not stop until you are 100% certain."
        ),
        tools=[investigate],
        checkpoint=3,
        checkpoint_scrutiny=CheckpointScrutiny.STRICT,
        max_turns=20,
    )
    agent.summarize_tool_output = False
    agent.narration = True

    try:
        result = await agent.run(
            "Investigate anomaly XJ-7. Keep going until you have a definitive answer."
        )
        print(f"\nAgent: {result}")
    except AntiSpinTerminated as e:
        print(f"\n  AntiSpinTerminated after {agent.turn_count} turns:")
        print(f"  {e}")


async def main():
    print("Nori anti-spin demo")
    await scenario_healthy()
    await scenario_spin()
    print(f"\n{DIVIDER}\nDone.\n{DIVIDER}")


asyncio.run(main())
