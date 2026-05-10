"""
Incident response exercise — Nori single-agent stress test.

A P0 incident: the order service is degraded with cascading failures.
Four bugs are planted (missing index, N+1 queries, connection leak, broken cache TTL).
One agent investigates, gets human approval, remediates, verifies, and writes a post-mortem.

Run:
    python exercises/incident_response/run.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import httpx

import config
import nori
from nori import Agent
from nori.tools import HumanInput
from nori.tools.bash import Bash
from nori.tools.file_search import FileSearch
from nori.tools.file_edit import FileEdit

from setup import setup, SERVICE_DIR, DB_PATH

EXERCISE_DIR = os.path.dirname(os.path.abspath(__file__))
DIVIDER = "=" * 70


# ── Auto-responder (acts as the on-call human approving the fix plan) ─────────

async def auto_responder(base_url: str, response: str, stop: asyncio.Event) -> None:
    """Poll for pending HITL requests and auto-approve."""
    async with httpx.AsyncClient() as client:
        while not stop.is_set():
            await asyncio.sleep(0.3)
            try:
                resp = await client.get(f"{base_url}/hitl/pending", timeout=2)
                for req in resp.json():
                    print(f"\n[auto-responder] Approving HITL request: {req['question'][:120]!r}...")
                    await client.post(
                        f"{base_url}/hitl/{req['id']}/respond",
                        json={"response": response},
                        timeout=2,
                    )
            except Exception:
                pass


# ── Agent ─────────────────────────────────────────────────────────────────────

def build_agent() -> Agent:
    agent = Agent(
        name="IncidentResponseAgent",
        system_prompt="You are a senior SRE on-call. Investigate the reported issue, identify root causes, get human approval before making changes, apply fixes, verify your fixes work by running the test suite, and write a post-mortem.",
        tools=[Bash, FileSearch, FileEdit, HumanInput],
        max_turns=config.MAX_TURNS,
    )
    agent.narration = True
    return agent


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    setup()

    cfg = nori.config.get_defaults().server
    base_url = f"http://{cfg.host}:{cfg.port}"

    agent = build_agent()

    stop = asyncio.Event()
    responder_task = asyncio.create_task(
        auto_responder(base_url, "Approved — apply all four fixes.", stop)
    )

    print(DIVIDER)
    print("Nori incident response exercise — P0 order service degradation")
    print(f"Service:   {SERVICE_DIR}")
    print(f"Database:  {DB_PATH}")
    print(f"HITL:      {base_url}")
    print(f"Model:     {config.MAIN_MODEL}")
    print(DIVIDER)
    print()

    result = await agent.run(
        f"Users are reporting errors on the order service at {SERVICE_DIR}. "
        f"The database is at {DB_PATH}. "
        f"Write the post-mortem to {EXERCISE_DIR}/postmortem.md if you find a problem."
    )

    stop.set()
    responder_task.cancel()

    from nori import server as _server
    await _server.shutdown()

    print(f"\n{DIVIDER}")
    print("INCIDENT RESPONSE COMPLETE")
    print(DIVIDER)
    print(result)
    print(f"\nTurns: {agent.turn_count}  |  Cost: ${agent.cost:.4f}")

    postmortem_path = os.path.join(EXERCISE_DIR, "postmortem.md")
    if os.path.exists(postmortem_path):
        print(f"Post-mortem: {postmortem_path}")
    else:
        print("Post-mortem: NOT WRITTEN")

    print(DIVIDER)


if __name__ == "__main__":
    asyncio.run(main())
