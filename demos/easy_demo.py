import sys, os

import asyncio

from nori import Agent, ContextWindow, Model, Provider
from nori.audit import AuditLogger
from nori.tools.bash import Bash


SYSTEM_PROMPT = """\
You are a file and shell agent. Execute tasks step by step using the Bash tool.
Always show the output of each command before moving to the next step.
"""

TASK = """\
Complete the following steps in order:

1. Create a file called /tmp/nori_demo.txt
2. Write the current date and time into it
3. Use curl to fetch weather for Austin TX from wttr.in (plain text format: curl 'wttr.in/Austin?format=3') and append the result to the file
4. cat the file to show its contents
5. Rename the file to /tmp/nori_demo_final.txt
6. cat the renamed file to confirm the rename worked and pipe it into a copy of the file
7. Delete the original file

Do each step explicitly and show all output.
"""

OLLAMA_MODEL = Model(id="gemma4:31b", base_url=Provider.OLLAMA.base_url, api_key=Provider.OLLAMA.api_key, context_window=ContextWindow.K24)

async def main():
    agent = Agent(
        name="DemoAgent",
        model=OLLAMA_MODEL,
        system_prompt=SYSTEM_PROMPT,
        tools=[Bash],
        max_turns=20,
    )
    agent.narration = True
    agent.auditor = AuditLogger("logs/easy_demo.audit.log")

    print("=" * 60)
    print("Nori demo — multi-step agentic bash task")
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
