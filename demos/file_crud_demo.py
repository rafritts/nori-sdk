"""
File CRUD demo: create, read, update, delete.

A scratchpad directory is planted at /tmp/nori_file_crud. The agent is given a
multi-step task that exercises all four file operations:

  1. Create   — write a new JSON config file
  2. Read     — read it back and report its contents
  3. Update   — edit a specific field in the file
  4. Delete   — remove the file via shell after confirming the edit

The demo verifies each step left the filesystem in the expected state before
reporting success.
"""

import asyncio
import os
import shutil

import config
from nori import Agent
from nori.audit import AuditLogger
from nori.tools.bash import Bash
from nori.tools.file_edit import FileEdit
from nori.tools.file_read import FileRead
from nori.tools.file_search import FileSearch
from nori.tools.file_write import FileWrite

WORKDIR = "/tmp/nori_file_crud"

SYSTEM_PROMPT = """\
You are a precise file management agent. You create, read, edit, and delete files
exactly as instructed. After each operation, confirm it succeeded before continuing.
"""

TASK = f"""\
Work inside {WORKDIR}. Complete these steps in order:

1. CREATE — write a file called config.json with this exact content:
   {{
     "app": "nori-demo",
     "version": "1.0.0",
     "debug": false
   }}

2. READ — read config.json and report its contents.

3. UPDATE — change the "version" field from "1.0.0" to "1.1.0" using FileEdit.
   Then read the file again to confirm the change.

4. DELETE — delete config.json using the shell (rm command).
   Confirm the file is gone by attempting to list it.

Report what you did at each step and confirm the final state.
"""


def setup() -> None:
    shutil.rmtree(WORKDIR, ignore_errors=True)
    os.makedirs(WORKDIR)


def cleanup() -> None:
    shutil.rmtree(WORKDIR, ignore_errors=True)


async def main() -> None:
    setup()

    agent = Agent(
        name="FileCRUD",
        system_prompt=SYSTEM_PROMPT,
        tools=[FileWrite, FileRead, FileEdit, FileSearch, Bash],
        max_turns=20,
    )
    agent.narration = True
    agent.auditor = AuditLogger("logs/file_crud_demo.audit.log")

    print("=" * 60)
    print("Nori file CRUD demo")
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
