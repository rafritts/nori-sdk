"""
Hard demo: broken repo recovery.

A Python project is planted at /tmp/nori_hard_demo with three bugs across
three files. The agent is given only the directory path and told to make all
tests pass. No hints about what is broken or where.

Bugs planted:
  stats.py     — typo in import (ImportError)
  transform.py — off-by-one in slice (wrong results)
  validator.py — swapped return values in clamp() (inverted logic)

Constraint: the agent must not modify test files.
"""

import asyncio
import textwrap

from nori import Agent, Model, ContextWindow, Provider
from nori.audit import AuditLogger
from nori.tools.bash import Bash
from nori.tools.file_edit import FileEdit
from nori.tools.file_search import FileSearch


BROKEN_FILES = {
    "/tmp/nori_hard_demo/stats.py": textwrap.dedent("""\
        from collectoins import Counter

        def word_freq(text):
            words = text.lower().split()
            return dict(Counter(words))
    """),

    "/tmp/nori_hard_demo/transform.py": textwrap.dedent("""\
        def top_n(items, n):
            \"\"\"Return the n largest items, sorted descending.\"\"\"
            sorted_items = sorted(items, reverse=True)
            return sorted_items[1:n + 1]
    """),

    "/tmp/nori_hard_demo/validator.py": textwrap.dedent("""\
        def clamp(value, lo, hi):
            \"\"\"Clamp value to [lo, hi].\"\"\"
            if value < lo:
                return hi
            if value > hi:
                return lo
            return value

        def is_valid_percentage(value):
            \"\"\"Return True if value is in [0, 100].\"\"\"
            return 0 <= value <= 100
    """),

    "/tmp/nori_hard_demo/test_stats.py": textwrap.dedent("""\
        from stats import word_freq

        def test_word_freq_counts():
            result = word_freq("the cat sat on the mat the cat")
            assert result["the"] == 3
            assert result["cat"] == 2
            assert result["sat"] == 1
    """),

    "/tmp/nori_hard_demo/test_transform.py": textwrap.dedent("""\
        from transform import top_n

        def test_top_n_basic():
            assert top_n([3, 1, 4, 1, 5, 9, 2, 6], 3) == [9, 6, 5]

        def test_top_n_single():
            assert top_n([7, 2, 5], 1) == [7]
    """),

    "/tmp/nori_hard_demo/test_validator.py": textwrap.dedent("""\
        from validator import clamp, is_valid_percentage

        def test_clamp_below():
            assert clamp(5, 10, 20) == 10

        def test_clamp_above():
            assert clamp(25, 10, 20) == 20

        def test_clamp_within():
            assert clamp(15, 10, 20) == 15

        def test_valid_percentage_bounds():
            assert is_valid_percentage(0) is True
            assert is_valid_percentage(100) is True
            assert is_valid_percentage(101) is False
            assert is_valid_percentage(-1) is False
    """),
}

SYSTEM_PROMPT = """\
You are a senior software engineer. You find and fix bugs by reading code and running tests.
You have a shell. Figure out what is broken yourself — do not ask for hints.
Do not modify any test files.
"""

TASK = """\
The Python project at /tmp/nori_hard_demo has failing tests. Make all tests pass.

Start by running: cd /tmp/nori_hard_demo && python -m pytest -v

Investigate each failure, fix the source file, and re-run until everything is green.
"""


def setup() -> None:
    import os
    os.makedirs("/tmp/nori_hard_demo", exist_ok=True)
    for path, content in BROKEN_FILES.items():
        with open(path, "w") as f:
            f.write(content)


def cleanup() -> None:
    import shutil
    shutil.rmtree("/tmp/nori_hard_demo", ignore_errors=True)


async def main() -> None:
    setup()

    agent = Agent(
        name="BugHunter",
        model=Model(id="gemma4:31b", provider=Provider.OLLAMA, context_window=ContextWindow.K24),
        system_prompt=SYSTEM_PROMPT,
        tools=[Bash, FileEdit, FileSearch],
        max_turns=25,
    )
    agent.narration = True
    agent.auditor = AuditLogger("logs/hard_demo.audit.log")

    print("=" * 60)
    print("Nori hard demo — broken repo recovery")
    print("=" * 60)
    print()

    try:
        result = await agent.run(TASK)
        print(f"\nAgent: {result}")
    finally:
        cleanup()
        agent.auditor.close()

    print(f"\nTurns: {agent.turn_count}  |  Cost: ${agent.cost:.4f}")


asyncio.run(main())
