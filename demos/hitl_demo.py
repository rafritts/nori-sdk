"""
Human-in-the-loop demo: shows the embedded server + HumanInput tool.

The agent asks for approval before proceeding. A background task acts as the
"human" — it polls GET /hitl/pending and auto-responds via POST /hitl/{id}/respond.

Run it:
    python demos/hitl_demo.py
"""

import asyncio

import httpx
import nori
from nori import Agent
from nori.tools import HumanInput

DIVIDER = "=" * 60

SYSTEM = (
    "You are a cautious assistant. Before taking any significant action, "
    "always use the HumanInput tool to ask for approval. "
    "After receiving approval, summarize what was approved and confirm you will proceed."
)

TASK = (
    "I need you to purge all log files older than 30 days from /var/log/app. "
    "Ask me for approval before doing anything."
)


async def auto_responder(base_url: str, cfg, response: str, stop: asyncio.Event) -> None:
    """Poll for pending HITL requests and respond automatically."""
    async with httpx.AsyncClient() as client:
        while not stop.is_set():
            await asyncio.sleep(0.3)
            # The token is generated when the server first starts (on the agent's
            # first HumanInput call), so read it live off the shared config.
            if not cfg.token:
                continue
            headers = {"X-Nori-Token": cfg.token}
            try:
                resp = await client.get(f"{base_url}/hitl/pending", headers=headers, timeout=2)
                for req in resp.json():
                    print(f"\n[auto-responder] question: {req['question']!r}")
                    print(f"[auto-responder] responding: {response!r}")
                    await client.post(
                        f"{base_url}/hitl/{req['id']}/respond",
                        json={"response": response},
                        headers=headers,
                        timeout=2,
                    )
            except Exception:
                pass  # server may not be ready yet on first poll


async def main() -> None:
    nori.configure(server=True)

    cfg = nori.config.get_defaults().server
    base_url = f"http://{cfg.host}:{cfg.port}"

    agent = Agent(
        name="CautiousAgent",
        system_prompt=SYSTEM,
        tools=[HumanInput],
    )
    agent.narration = True

    stop = asyncio.Event()
    responder_task = asyncio.create_task(
        auto_responder(base_url, cfg, "Yes, approved — please proceed.", stop)
    )

    print(DIVIDER)
    print("HITL demo  (server mode — auto-responder acting as human)")
    print(f"Server:    {base_url}")
    print(f"Model:     {agent.model}")
    print(DIVIDER)

    result = await agent.run(TASK)

    stop.set()
    responder_task.cancel()

    from nori import server as _server
    await _server.shutdown()

    print(f"\n{DIVIDER}")
    print("Final response:")
    print(result)
    print(f"\nTurns: {agent.turn_count}  |  Cost: ${agent.cost:.4f}")
    print(DIVIDER)


asyncio.run(main())
