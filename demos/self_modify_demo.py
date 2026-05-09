"""
Demonstrates Nori's self-modification tiers.

Agents can be granted increasing levels of self-modification capability:

  self_custodian  — can update its own system prompt
  self_modify     — can also add/remove tools at runtime
  self_mutation   — can also switch models and adjust max_turns

Each tier is additive. The agent uses these as regular tools — the model
decides when and why to invoke them.
"""

import config
import asyncio

from nori import Agent, SelfModify
from nori.audit import AuditLogger
from nori.tool import tool

DIVIDER = "=" * 60


def section(title: str) -> None:
    print(f"\n{DIVIDER}")
    print(title)
    print(DIVIDER)


# ── Scenario 1: Custodian — update system prompt ──────────────────────────────

async def scenario_custodian(auditor: AuditLogger):
    section("SCENARIO 1 — self_custodian: agent updates its own system prompt")

    agent = Agent(
        name="CustodianAgent",
        system_prompt="You are a generic assistant.",
        self_modify=SelfModify.CUSTODIAN,
    )
    agent.narration = True
    agent.auditor = auditor

    print(f"System prompt before: {agent.system_prompt!r}")

    result = await agent.run(
        "Update your system prompt to say you are a specialized Python coding assistant, "
        "then confirm the change by telling me your new role."
    )

    print(f"\nAgent: {result}")
    print(f"System prompt after:  {agent.system_prompt!r}")


# ── Scenario 2: Modify — add and remove tools at runtime ─────────────────────

@tool(summarize_output=False)
def celsius_to_fahrenheit(celsius: float) -> str:
    """Convert a temperature from Celsius to Fahrenheit."""
    return f"{celsius * 9/5 + 32:.1f}°F"


async def scenario_modify(auditor: AuditLogger):
    section("SCENARIO 2 — self_modify: agent removes a tool mid-run")

    agent = Agent(
        name="ModifyAgent",
        system_prompt=(
            "You are a utility agent. If asked to restrict your own capabilities, "
            "use remove_tool to do so, then confirm."
        ),
        tools=[celsius_to_fahrenheit],
        self_modify=SelfModify.MODIFY,
    )
    agent.narration = True
    agent.auditor = auditor

    print(f"Tools before: {list(agent._tools.keys())}")

    result = await agent.run(
        "Convert 100°C to Fahrenheit, then remove the celsius_to_fahrenheit tool "
        "since it's no longer needed, and confirm it's gone."
    )

    print(f"\nAgent: {result}")
    print(f"Tools after:  {list(agent._tools.keys())}")


# ── Scenario 3: Mutation — switch model mid-run ───────────────────────────────

async def scenario_mutation(auditor: AuditLogger):
    section("SCENARIO 3 — self_mutation: agent switches to a lighter model mid-run")

    agent = Agent(
        name="MutationAgent",
        system_prompt=(
            "You are a resourceful agent. If a task is simple, switch to a lighter "
            "model to save cost, then complete the task."
        ),
        self_modify=SelfModify.MUTATION,
    )
    agent.narration = True
    agent.auditor = auditor

    print(f"Model before: {agent.model!r}")

    result = await agent.run(
        "This next task is very simple — just say hello. Switch to grok-3-mini first "
        "to save cost, then greet the user."
    )

    print(f"\nAgent: {result}")
    print(f"Model after:  {agent.model!r}")


async def main():
    print("Nori self-modification demo")
    auditor = AuditLogger("logs/self_modify_demo.audit.log")
    await scenario_custodian(auditor)
    await scenario_modify(auditor)
    await scenario_mutation(auditor)
    auditor.close()
    print(f"\n{DIVIDER}\nDone.\n{DIVIDER}")


asyncio.run(main())
