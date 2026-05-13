"""
OpenAI-compatible chat server backed by a nori Agent.

Usage:
    from nori.chatbot import serve
    from nori import Agent, Model

    def make_agent():
        return Agent(name="assistant", model=Model.GPT4O_MINI, ...)

    serve(make_agent, port=8000)

Then point Open WebUI (or any OpenAI-compatible client) at http://localhost:8000/v1.
"""

import json
import logging
import time
import uuid
from typing import AsyncGenerator, Callable

logger = logging.getLogger("nori.chatbot")


def make_app(agent_factory: Callable, model_id: str = "nori") -> "FastAPI":
    from fastapi import FastAPI
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel

    app = FastAPI(title="nori-chatbot", docs_url=None, redoc_url=None)

    class Message(BaseModel):
        role: str
        content: str

    class ChatRequest(BaseModel):
        model: str = model_id
        messages: list[Message]
        stream: bool = False

    @app.get("/v1/models")
    async def list_models():
        return {
            "object": "list",
            "data": [{"id": model_id, "object": "model", "created": int(time.time()), "owned_by": "nori"}],
        }

    @app.post("/v1/chat/completions")
    async def chat(req: ChatRequest):
        agent = agent_factory()

        last_user_idx = max(
            (i for i, m in enumerate(req.messages) if m.role == "user"),
            default=None,
        )
        if last_user_idx is None:
            return {"error": "no user message in request"}

        # Pre-populate agent history with prior turns so the agent has full context.
        for msg in req.messages[:last_user_idx]:
            agent._history.append({"role": msg.role, "content": msg.content})

        prompt = req.messages[last_user_idx].content
        result = await agent.run(prompt)

        cid = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())
        tc = agent.token_counts

        logger.debug("chat cid=%s turns=%d tokens=%d", cid, agent.turn_count, tc["prompt"] + tc["completion"])

        if req.stream:
            return StreamingResponse(
                _stream(result, cid, created, model_id),
                media_type="text/event-stream",
            )

        return {
            "id": cid,
            "object": "chat.completion",
            "created": created,
            "model": model_id,
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": result}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": tc["prompt"], "completion_tokens": tc["completion"], "total_tokens": tc["prompt"] + tc["completion"]},
        }

    return app


async def _stream(text: str, cid: str, created: int, model_id: str) -> AsyncGenerator[str, None]:
    yield _chunk(cid, created, model_id, {"role": "assistant", "content": ""})
    words = text.split(" ")
    for i, word in enumerate(words):
        content = word if i == len(words) - 1 else word + " "
        yield _chunk(cid, created, model_id, {"content": content})
    yield _chunk(cid, created, model_id, {}, finish_reason="stop")
    yield "data: [DONE]\n\n"


def _chunk(cid: str, created: int, model_id: str, delta: dict, finish_reason=None) -> str:
    payload = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model_id,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(payload)}\n\n"


def serve(agent_factory: Callable, host: str = "0.0.0.0", port: int = 8000, model_id: str = "nori") -> None:
    """Start an OpenAI-compatible chat server backed by a nori Agent.

    agent_factory must be a zero-argument callable that returns a fresh Agent
    per request — required so each user gets clean state and concurrent requests
    don't share history.
    """
    try:
        import uvicorn
    except ImportError:
        raise ImportError("uvicorn is required. Install with: uv add 'nori[server]'")

    app = make_app(agent_factory, model_id=model_id)
    logger.info("nori chatbot listening on http://%s:%d/v1", host, port)
    uvicorn.run(app, host=host, port=port)
