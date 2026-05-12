"""
Notify demo: signal task completion and failures via Notify.

The agent is given a simple health-check task: inspect three "service config"
files planted at /tmp/nori_notify_demo, identify any problems, and send a
Notify for each finding — urgent if a problem is critical, normal otherwise.
A final summary notification is sent when the check is complete.

With no Slack or webhook configured, Notify prints to stdout so the calls are
visible inline with narration output.
"""

import asyncio
import os
import shutil
import textwrap

import config
from nori import Agent
from nori.audit import AuditLogger
from nori.tools.file_read import FileRead
from nori.tools.notify import Notify


WORKDIR = "/tmp/nori_notify_demo"

SERVICE_FILES = {
    "api.conf": textwrap.dedent("""\
        [service]
        name = api
        port = 8080
        timeout = 30
        max_connections = 500
        debug = false
    """),
    "worker.conf": textwrap.dedent("""\
        [service]
        name = worker
        port = 9000
        timeout = 0
        max_connections = 50
        debug = true
    """),
    "db_proxy.conf": textwrap.dedent("""\
        [service]
        name = db_proxy
        port = 5432
        timeout = 10
        max_connections = 10
        debug = false
        # FIXME: auth disabled for testing
        auth = none
    """),
}

SYSTEM_PROMPT = """\
You are an automated ops agent. You review service configuration files for
problems and send notifications about your findings. Use Notify with urgent=True
for critical issues (security risks, zero timeouts) and urgent=False for
warnings. Always send a final summary notification when your check is complete.
"""

TASK = f"""\
Read each service config file in {WORKDIR} and check for problems:

  - timeout = 0 is a critical issue (requests will hang forever)
  - debug = true in a service config is a warning
  - auth = none is a critical security issue

For each problem found, send a Notify immediately describing the service name,
the problem, and its severity.

After checking all three files, send one final Notify summarising how many
critical issues and warnings were found across all services.
"""


def setup() -> None:
    shutil.rmtree(WORKDIR, ignore_errors=True)
    os.makedirs(WORKDIR)
    for name, content in SERVICE_FILES.items():
        with open(os.path.join(WORKDIR, name), "w") as f:
            f.write(content)


def cleanup() -> None:
    shutil.rmtree(WORKDIR, ignore_errors=True)


async def main() -> None:
    setup()

    agent = Agent(
        name="OpsAgent",
        system_prompt=SYSTEM_PROMPT,
        tools=[FileRead, Notify],
        max_turns=20,
    )
    agent.narration = True
    agent.auditor = AuditLogger("logs/notify_demo.audit.log")

    print("=" * 60)
    print("Nori notify demo")
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
