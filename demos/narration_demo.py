"""
Demonstrates Nori's narration system.

Narration fires before each tool call with the tool name and the agent's
stated reason. Useful for real-time visibility into what the agent is doing
without waiting for the full run to complete.

Shows:
  1. Default narration (prints to stdout)
  2. Custom on_narration callback
  3. narrator_prefix for multi-agent disambiguation
"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio

from nori import Agent, Model
from nori.tool import tool

DIVIDER = "=" * 60


@tool
def check_service(name: str) -> str:
    """Check whether a named service is running."""
    # Simulate mixed health results
    healthy = {"api-gateway", "auth-service"}
    return "UP" if name in healthy else "DOWN"


@tool
def get_service_logs(name: str) -> str:
    """Fetch the last few log lines for a service."""
    logs = {
        "api-gateway": "INFO  Request processed in 42ms\nINFO  Health check OK",
        "auth-service": "INFO  Token issued\nINFO  Health check OK",
        "worker": "ERROR Failed to connect to queue\nERROR Retrying (3/5)...",
        "scheduler": "WARN  Job overdue by 4 minutes\nERROR Missed 2 executions",
    }
    return logs.get(name, f"No logs found for {name}.")


SERVICES = ["api-gateway", "auth-service", "worker", "scheduler"]
TASK = f"Check the status of these services and pull logs for any that are down: {', '.join(SERVICES)}. Summarize findings."


def section(title: str) -> None:
    print(f"\n{DIVIDER}")
    print(title)
    print(DIVIDER)


async def scenario_default_narration():
    section("SCENARIO 1 — Default narration (stdout)")

    agent = Agent(
        name="OpsAgent",
        model=Model(id="grok-4.3"),
        system_prompt="You are an ops agent. Check services and report issues.",
        tools=[check_service, get_service_logs],
    )
    agent.narration = True

    result = await agent.run(TASK)
    print(f"\nAgent: {result}")


async def scenario_custom_callback():
    section("SCENARIO 2 — Custom on_narration callback")

    events = []

    def capture(text: str) -> None:
        events.append(text)
        print(f"  [NARRATION EVENT] {text}")

    agent = Agent(
        name="OpsAgent",
        model=Model(id="grok-4.3"),
        system_prompt="You are an ops agent. Check services and report issues.",
        tools=[check_service, get_service_logs],
    )
    agent.narration = True
    agent.on_narration = capture

    result = await agent.run(TASK)
    print(f"\nAgent: {result}")
    print(f"\nTotal narration events captured: {len(events)}")


async def scenario_narrator_prefix():
    section("SCENARIO 3 — narrator_prefix for multi-agent disambiguation")

    infra = Agent(
        name="InfraAgent",
        model=Model(id="grok-4.3"),
        system_prompt="You are an infrastructure agent.",
        tools=[check_service],
    )
    infra.narration = True
    infra.narrator_prefix = "[infra] "

    app = Agent(
        name="AppAgent",
        model=Model(id="grok-4.3"),
        system_prompt="You are an application agent.",
        tools=[get_service_logs],
    )
    app.narration = True
    app.narrator_prefix = "[app]   "

    print("Running both agents concurrently...\n")
    infra_result, app_result = await asyncio.gather(
        infra.run(f"Check status of: {', '.join(SERVICES)}"),
        app.run("Get logs for worker and scheduler."),
    )
    print(f"\nInfraAgent: {infra_result}")
    print(f"\nAppAgent:   {app_result}")


async def main():
    print("Nori narration demo")
    await scenario_default_narration()
    await scenario_custom_callback()
    await scenario_narrator_prefix()
    print(f"\n{DIVIDER}\nDone.\n{DIVIDER}")


asyncio.run(main())
