import asyncio
import logging
from contextvars import ContextVar
from datetime import datetime, timezone

logger = logging.getLogger("nori.server")

# Set by Agent.run() so HumanInput can label pending requests with the agent name.
_agent_name_var: ContextVar[str] = ContextVar("nori_agent_name", default="unknown")

# id -> {future, agent, question, options, created_at}
_pending: dict[str, dict] = {}

_server_task: asyncio.Task | None = None


async def ensure_started(cfg) -> None:
    global _server_task
    if _server_task is not None:
        return
    try:
        import uvicorn
    except ImportError:
        raise ImportError(
            "fastapi and uvicorn are required for the embedded server. "
            "Install with: uv add 'nori[server]'"
        )

    app = _make_app()
    uv_cfg = uvicorn.Config(app, host=cfg.host, port=cfg.port, log_level="warning")
    server = uvicorn.Server(uv_cfg)
    _server_task = asyncio.create_task(server.serve())
    # Give uvicorn a moment to bind before accepting requests.
    await asyncio.sleep(0.15)
    logger.info("nori server started on http://%s:%d", cfg.host, cfg.port)


def register_pending(
    request_id: str,
    future: asyncio.Future,
    agent: str,
    question: str,
    options: list,
) -> None:
    _pending[request_id] = {
        "future": future,
        "agent": agent,
        "question": question,
        "options": options,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def unregister_pending(request_id: str) -> None:
    _pending.pop(request_id, None)


def _make_app():
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel

    app = FastAPI(title="nori", docs_url=None, redoc_url=None)

    class RespondBody(BaseModel):
        response: str

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/hitl/pending")
    async def hitl_pending():
        return [
            {
                "id": rid,
                "agent": info["agent"],
                "question": info["question"],
                "options": info["options"],
                "created_at": info["created_at"],
            }
            for rid, info in _pending.items()
        ]

    @app.post("/hitl/{request_id}/respond")
    async def hitl_respond(request_id: str, body: RespondBody):
        info = _pending.get(request_id)
        if info is None or info["future"].done():
            raise HTTPException(status_code=404, detail="Unknown or already resolved request")
        info["future"].set_result(body.response)
        return {"ok": True}

    return app
