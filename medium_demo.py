import asyncio

from nori import Agent
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


async def main():
    agent = Agent(
        name="MediumDemoAgent",
        system_prompt=SYSTEM_PROMPT,
        tools=[Bash],
        max_turns=20,
    )
    agent.narration = True
    agent.summarize_tool_output = False

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
