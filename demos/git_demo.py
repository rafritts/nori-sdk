"""
Git demo: branch, commit, and inspect a local repository.

A throwaway git repo is planted at /tmp/nori_git_demo with an initial commit
and two starter files. The agent is asked to:

  1. Check status and read the recent log.
  2. Create a feature branch.
  3. Add a new file (CHANGELOG.md) and commit it.
  4. Return to main and report what changed.
"""

import asyncio
import os
import shutil
import subprocess
import textwrap

import config
from nori import Agent
from nori.audit import AuditLogger
from nori.tools.file_write import FileWrite
from nori.tools.git import Git


REPO = "/tmp/nori_git_demo"

STARTER_FILES = {
    "README.md": textwrap.dedent("""\
        # nori-git-demo

        A throwaway repo used by the Nori git demo.
    """),
    "app.py": textwrap.dedent("""\
        def greet(name: str) -> str:
            return f"Hello, {name}!"
    """),
}

SYSTEM_PROMPT = """\
You are a careful git assistant. Use the Git tool for all version-control operations.
Always confirm each step succeeded before continuing.
"""

TASK = f"""\
Work with the git repository at {REPO}. Complete these steps in order:

1. STATUS & LOG — check the current status and show the last 5 commits.
2. BRANCH — create and switch to a new branch called feature/changelog.
3. ADD FILE — write a new file CHANGELOG.md at {REPO}/CHANGELOG.md with:
   ## [Unreleased]
   - Initial changelog entry added by agent.
4. COMMIT — stage CHANGELOG.md and commit it with message "Add CHANGELOG".
5. RETURN — switch back to main (or master), then show the branch list.

Report what you did at each step.
"""


def setup() -> None:
    shutil.rmtree(REPO, ignore_errors=True)
    os.makedirs(REPO)
    subprocess.run(["git", "init", "-b", "main"], cwd=REPO, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "demo@nori.local"], cwd=REPO, check=True)
    subprocess.run(["git", "config", "user.name", "Nori Demo"], cwd=REPO, check=True)
    for name, content in STARTER_FILES.items():
        with open(os.path.join(REPO, name), "w") as f:
            f.write(content)
    subprocess.run(["git", "add", "-A"], cwd=REPO, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=REPO, check=True, capture_output=True)


def cleanup() -> None:
    shutil.rmtree(REPO, ignore_errors=True)


async def main() -> None:
    setup()

    SafeGit = Git.bind(repo_path=REPO)

    agent = Agent(
        name="GitAgent",
        system_prompt=SYSTEM_PROMPT,
        tools=[SafeGit, FileWrite],
        max_turns=20,
    )
    agent.narration = True
    agent.auditor = AuditLogger("logs/git_demo.audit.log")

    print("=" * 60)
    print("Nori git demo")
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
