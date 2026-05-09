import config
import asyncio

from nori import Agent
from nori.audit import AuditLogger
from nori.tools.bash import Bash


SYSTEM_PROMPT = """\
You are a system analyst. Use shell commands to investigate and reason about what you find.
Don't assume anything — observe, then conclude.
"""

TASK = """\
Something is eating disk space in /tmp. Figure out what's going on:
find the largest files or directories, determine if any of them look like they were \
created recently or are accumulating, and write a short summary report to /tmp/disk_report.txt \
that includes your findings and a recommendation. Then show me the report.
"""


def plant_junk():
    """Create some suspicious-looking files in /tmp before the agent runs."""
    import os, subprocess
    # A few large-ish files with plausible names
    subprocess.run("dd if=/dev/urandom of=/tmp/app_cache_1.bin bs=1M count=5 2>/dev/null", shell=True)
    subprocess.run("dd if=/dev/urandom of=/tmp/app_cache_2.bin bs=1M count=8 2>/dev/null", shell=True)
    subprocess.run("dd if=/dev/urandom of=/tmp/core.12345 bs=1M count=12 2>/dev/null", shell=True)
    # A directory that looks like a log accumulation
    os.makedirs("/tmp/app_logs", exist_ok=True)
    for i in range(6):
        subprocess.run(f"dd if=/dev/urandom of=/tmp/app_logs/service_{i}.log bs=512K count=1 2>/dev/null", shell=True)


async def main():
    plant_junk()

    agent = Agent(
        name="Medium1DemoAgent",
        system_prompt=SYSTEM_PROMPT,
        tools=[Bash],
        max_turns=20,
    )
    agent.auditor = AuditLogger("logs/medium_demo.audit.log")
    agent.narration = True
    print("=" * 60)
    print("Nori medium demo — open-ended system investigation")
    print("=" * 60)
    print()

    result = await agent.run(TASK)

    print()
    print("=" * 60)
    print("Final response:")
    print("=" * 60)
    print(result)
    print()
    print(f"Turns: {agent.turn_count}  |  Tool calls: {len(agent.tool_calls)}  |  Cost: ${agent.cost:.4f}")


asyncio.run(main())
