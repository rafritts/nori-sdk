"""
Demonstrates the difference between standard Python logging and the nori audit stream.

- nori.agent / nori.narration: configured like any Python logger — handler, formatter, done.
- nori.audit: structured JSON-lines event stream, opt-in via agent.auditor.
"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
import logging
import logging.handlers

from nori import Agent
from nori.audit import AuditLogger
from nori.tool import tool

LOG_FILE = "logs/observability_demo.log"
AUDIT_FILE = "logs/observability_demo.audit.log"


# ── Standard Python logging setup ────────────────────────────────────────────
# This is exactly what any Python developer expects to do — nothing special.

handler = logging.FileHandler(LOG_FILE, mode="w")
handler.setLevel(logging.DEBUG)
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s"))

logging.getLogger("nori").setLevel(logging.DEBUG)
logging.getLogger("nori").addHandler(handler)


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def get_system_info() -> str:
    """Return basic system info."""
    import platform
    return f"{platform.system()} {platform.release()} ({platform.machine()})"


@tool
def get_uptime() -> str:
    """Return system uptime."""
    import subprocess
    return subprocess.check_output("uptime -p", shell=True, text=True).strip()


@tool
def get_load() -> str:
    """Return current CPU load averages."""
    import os
    avg = os.getloadavg()
    return f"1m={avg[0]:.2f}  5m={avg[1]:.2f}  15m={avg[2]:.2f}"


# ── Run ───────────────────────────────────────────────────────────────────────

async def main():
    agent = Agent(
        name="ObservabilityDemo",
        system_prompt="You are a system info agent. Use your tools to answer questions.",
        tools=[get_system_info, get_uptime, get_load],
    )
    agent.summarize_tool_output = False
    agent.auditor = AuditLogger(AUDIT_FILE)

    print("Running agent...\n")
    result = await agent.run(
        "What OS am I on, how long has this machine been up, and what's the current load?"
    )
    print(f"Agent: {result}\n")

    # ── Show both outputs side by side ────────────────────────────────────────

    print("=" * 60)
    print(f"STANDARD PYTHON LOG  ({LOG_FILE})")
    print("=" * 60)
    with open(LOG_FILE) as f:
        print(f.read())

    print("=" * 60)
    print(f"AUDIT STREAM  ({AUDIT_FILE})")
    print("=" * 60)
    with open(AUDIT_FILE) as f:
        for line in f:
            print(json.dumps(json.loads(line), indent=2))
            print()


asyncio.run(main())
