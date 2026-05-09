import asyncio

from nori import Agent, Model, Provider
from nori.audit import AuditLogger
from nori.tools.bash import Bash


SYSTEM_PROMPT = """\
You are a senior software engineer. You write correct, minimal code and verify your work.
You have access to a shell. Think carefully before each step.
"""

TASK = """\
Write a Python script at /tmp/wordfreq.py that:
- accepts a filename as a command-line argument
- reads the file, tokenizes it into words (lowercase, strip punctuation)
- prints the top 10 most frequent words with their counts, formatted as a table

Then:
- generate a test input file at /tmp/test_input.txt with at least 5 distinct words \
appearing different numbers of times (make it non-trivial — don't just repeat one word)
- run the script against the test file
- verify the output is sorted correctly and the counts are accurate by independently \
counting the words yourself with shell tools
- if anything is wrong, fix the script and re-verify
- once verified, clean up both files
"""


async def main():
    agent = Agent(
        name="Medium2Agent",
        model=Model(id="grok-4.3", provider=Provider.XAI),
        system_prompt=SYSTEM_PROMPT,
        tools=[Bash],
        max_turns=30,
    )
    agent.narration = True
    agent.auditor = AuditLogger("logs/hard_demo.audit.log")

    print("=" * 60)
    print("Nori hard demo — write, test, verify, and self-correct")
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
