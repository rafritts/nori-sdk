import asyncio
import logging
import secrets
from contextvars import ContextVar
from datetime import datetime, timezone

logger = logging.getLogger("nori.server")

# Set by Agent.run() so HumanInput can label pending requests with the agent name.
_agent_name_var: ContextVar[str] = ContextVar("nori_agent_name", default="unknown")

# id -> {future, agent, question, options, created_at}
_pending: dict[str, dict] = {}

_server_task: asyncio.Task | None = None
_uvicorn_server = None  # uvicorn.Server instance, kept for graceful shutdown


async def ensure_started(cfg) -> None:
    global _server_task, _uvicorn_server
    if _server_task is not None:
        return
    try:
        import uvicorn
    except ImportError:
        raise ImportError(
            "fastapi and uvicorn are required for the embedded server. "
            "Install with: uv add 'nori[server]'"
        )

    if not cfg.token:
        cfg.token = secrets.token_urlsafe(32)
    app = _make_app(cfg.token)
    uv_cfg = uvicorn.Config(app, host=cfg.host, port=cfg.port, log_level="warning")
    _uvicorn_server = uvicorn.Server(uv_cfg)
    _server_task = asyncio.create_task(_uvicorn_server.serve())
    # Give uvicorn a moment to bind before accepting requests.
    await asyncio.sleep(0.15)
    logger.info(
        "nori server started on http://%s:%d — HITL endpoints require header "
        "'X-Nori-Token: %s'", cfg.host, cfg.port, cfg.token,
    )


async def shutdown() -> None:
    global _server_task, _uvicorn_server
    if _uvicorn_server is not None:
        _uvicorn_server.should_exit = True
        if _server_task is not None:
            await _server_task
    _server_task = None
    _uvicorn_server = None


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


def _pending_view() -> list[dict]:
    """Live waits plus journaled questions whose answer has not been committed."""
    rows = []
    seen: set[str] = set()
    for rid, info in _pending.items():
        if info["future"].done():
            continue
        seen.add(rid)
        rows.append({
            "id": rid,
            "agent": info["agent"],
            "question": info["question"],
            "options": info["options"],
            "created_at": info["created_at"],
        })
    from nori import durable
    journal = durable.get_journal()
    if journal is None:
        return rows
    for row in journal.pending_hitl():
        if row["request_id"] in seen:
            continue
        rows.append({
            "id": row["request_id"],
            "agent": row.get("agent_name") or "unknown",
            "question": row.get("question") or "",
            "options": row.get("options") or [],
            "created_at": row.get("created_at"),
        })
    return rows


def _make_app(token: str | None = None):
    from fastapi import FastAPI, Header, HTTPException
    from pydantic import BaseModel

    app = FastAPI(title="nori", docs_url=None, redoc_url=None)

    class RespondBody(BaseModel):
        response: str

    def _auth(supplied: str | None) -> None:
        if token and not (supplied and secrets.compare_digest(supplied, token)):
            raise HTTPException(status_code=401, detail="Missing or invalid X-Nori-Token")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/hitl/pending")
    async def hitl_pending(x_nori_token: str | None = Header(default=None)):
        _auth(x_nori_token)
        return _pending_view()

    @app.post("/hitl/{request_id}/respond")
    async def hitl_respond(
        request_id: str, body: RespondBody, x_nori_token: str | None = Header(default=None)
    ):
        _auth(x_nori_token)
        # Commit the answer before waking the agent. A kill after this returns
        # still leaves the response in the journal for resume.
        from nori import durable
        journal = durable.get_journal()
        saved = "missing"
        if journal is not None:
            saved = journal.save_hitl_response(request_id, body.response)
        info = _pending.get(request_id)
        if info is not None and not info["future"].done():
            info["future"].set_result(body.response)
            return {"ok": True}
        if saved == "saved":
            return {"ok": True}
        raise HTTPException(status_code=404, detail="Unknown or already resolved request")

    return app
