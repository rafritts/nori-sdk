"""
Demonstrates Nori's permission system.

Agents accept either an allow list OR a deny list (not both) with fnmatch glob support.
Attempting to call a blocked tool raises PermissionError and halts the run.

Three scenarios:
  1. No restrictions  — all tools available
  2. Allow list       — only explicitly listed tools can be called
  3. Deny list        — all tools available except explicitly blocked ones
"""

import asyncio

from nori import Agent, Model, Permissions
from nori.audit import AuditLogger
from nori.exceptions import PermissionError
from nori.tool import tool


@tool
def read_file(path: str) -> str:
    """Read a file from disk."""
    try:
        return open(path).read()
    except FileNotFoundError:
        return f"[file not found: {path}]"


@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file on disk."""
    open(path, "w").write(content)
    return f"Written to {path}."


@tool
def delete_file(path: str) -> str:
    """Delete a file from disk."""
    import os
    os.remove(path)
    return f"Deleted {path}."


ALL_TOOLS = [read_file, write_file, delete_file]
DIVIDER = "=" * 60


def section(title: str) -> None:
    print(f"\n{DIVIDER}")
    print(title)
    print(DIVIDER)


async def scenario_no_restrictions(auditor: AuditLogger):
    section("SCENARIO 1 — No restrictions (all tools available)")
    agent = Agent(
        name="UnrestrictedAgent",
        model=Model(id="grok-4.3"),
        system_prompt="You are a file agent. Use your tools to complete tasks.",
        tools=ALL_TOOLS,
    )
    agent.narration = True
    agent.auditor = auditor
    agent.on_tool_result = lambda name, result, call_id, trace_id: print(f"  [{name}] → {result.strip()}")

    result = await agent.run(
        "Write 'hello from nori' to /tmp/perm_demo.txt, then read it back, then delete it."
    )
    print(f"\nAgent: {result}")
    print(f"Tool calls: {[tc['name'] for tc in agent.tool_calls]}")


async def scenario_allow_list(auditor: AuditLogger):
    section("SCENARIO 2 — Allow list: only 'read_file' permitted")
    agent = Agent(
        name="ReadOnlyAgent",
        model=Model(id="grok-4.3"),
        system_prompt="You are a file agent. Use your tools to complete tasks.",
        tools=ALL_TOOLS,
        permissions=Permissions(allow=["read_file"]),
    )
    agent.narration = True
    agent.auditor = auditor
    agent.on_tool_result = lambda name, result, call_id, trace_id: print(f"  [{name}] → {result.strip()}")

    print("Attempting: write then read then delete...")
    try:
        result = await agent.run(
            "Write 'secret' to /tmp/perm_demo.txt, read it back, then delete it."
        )
        print(f"\nAgent: {result}")
    except PermissionError as e:
        print(f"\n  PermissionError: {e}")
    print(f"Tool calls attempted: {[tc['name'] for tc in agent.tool_calls]}")


async def scenario_deny_list(auditor: AuditLogger):
    section("SCENARIO 3 — Deny list: 'delete_file' blocked")
    agent = Agent(
        name="NoDeleteAgent",
        model=Model(id="grok-4.3"),
        system_prompt="You are a file agent. Use your tools to complete tasks.",
        tools=ALL_TOOLS,
        permissions=Permissions(deny=["delete_file"]),
    )
    agent.narration = True
    agent.auditor = auditor
    agent.on_tool_result = lambda name, result, call_id, trace_id: print(f"  [{name}] → {result.strip()}")

    print("Attempting: write, read, then delete...")
    try:
        result = await agent.run(
            "Write 'hello' to /tmp/perm_demo.txt, read it back, then delete it."
        )
        print(f"\nAgent: {result}")
    except PermissionError as e:
        print(f"\n  PermissionError: {e}")
    print(f"Tool calls attempted: {[tc['name'] for tc in agent.tool_calls]}")


async def main():
    print("Nori permissions demo")
    auditor = AuditLogger("logs/permissions_demo.audit.log")

    await scenario_no_restrictions(auditor)
    await scenario_allow_list(auditor)
    await scenario_deny_list(auditor)
    auditor.close()

    print(f"\n{DIVIDER}")
    print("Done.")
    print(DIVIDER)


asyncio.run(main())
