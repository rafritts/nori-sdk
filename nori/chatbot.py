"""
OpenAI-compatible chat server backed by a nori Agent.

Usage:
    from nori.chatbot import serve
    from nori import Agent

    def make_agent():
        return Agent(name="assistant", ...)

    serve(make_agent, port=7732)

Then point Open WebUI (or any OpenAI-compatible client) at http://localhost:7732/v1.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import AsyncGenerator, Callable

logger = logging.getLogger("nori.chatbot")


def make_app(agent_factory: Callable, model_id: str = "nori", narration: bool = True) -> "FastAPI":
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel

    app = FastAPI(title="nori-chatbot", docs_url=None, redoc_url=None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

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

        for msg in req.messages[:last_user_idx]:
            agent._history.append({"role": msg.role, "content": msg.content})

        prompt = req.messages[last_user_idx].content
        cid = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())

        if req.stream:
            queue: asyncio.Queue = asyncio.Queue()

            if narration:
                agent.narration = True
                def _on_narration(msg):
                    print(msg, flush=True)
                    queue.put_nowait(("narration", msg))
                agent.on_narration = _on_narration

            async def _run():
                try:
                    result = await agent.run(prompt)
                    tc = agent.token_counts
                    logger.debug("chat cid=%s turns=%d tokens=%d", cid, agent.turn_count, tc["prompt"] + tc["completion"])
                    queue.put_nowait(("done", result))
                except Exception as e:
                    queue.put_nowait(("error", str(e)))

            asyncio.create_task(_run())

            return StreamingResponse(
                _stream_live(queue, cid, created, model_id),
                media_type="text/event-stream",
            )

        # Non-streaming: run to completion, prepend narration as <think> block.
        narration_lines: list[str] = []
        if narration:
            agent.narration = True
            def _collect(msg):
                print(msg, flush=True)
                narration_lines.append(msg)
            agent.on_narration = _collect

        result = await agent.run(prompt)

        if narration_lines:
            result = f"<think>\n{chr(10).join(narration_lines)}\n</think>\n{result}"

        tc = agent.token_counts
        logger.debug("chat cid=%s turns=%d tokens=%d", cid, agent.turn_count, tc["prompt"] + tc["completion"])

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


async def _stream_live(queue: asyncio.Queue, cid: str, created: int, model_id: str) -> AsyncGenerator[str, None]:
    in_think = False

    while True:
        type_, data = await queue.get()

        if type_ == "narration":
            if not in_think:
                yield _chunk(cid, created, model_id, {"role": "assistant", "content": "<think>\n"})
                in_think = True
            yield _chunk(cid, created, model_id, {"content": data + "\n"})

        elif type_ == "done":
            if in_think:
                yield _chunk(cid, created, model_id, {"content": "</think>\n"})
            words = data.split(" ")
            for i, word in enumerate(words):
                content = word if i == len(words) - 1 else word + " "
                yield _chunk(cid, created, model_id, {"content": content})
            yield _chunk(cid, created, model_id, {}, finish_reason="stop")
            yield "data: [DONE]\n\n"
            break

        elif type_ == "error":
            yield _chunk(cid, created, model_id, {"content": f"Error: {data}"}, finish_reason="stop")
            yield "data: [DONE]\n\n"
            break


def _chunk(cid: str, created: int, model_id: str, delta: dict, finish_reason=None) -> str:
    payload = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model_id,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(payload)}\n\n"


def serve(
    agent_factory: Callable,
    host: str = "0.0.0.0",
    port: int = 7732,
    model_id: str = "nori",
    narration: bool = True,
) -> None:
    """Start an OpenAI-compatible chat server backed by a nori Agent.

    agent_factory must be a zero-argument callable that returns a fresh Agent
    per request — required so each user gets clean state and concurrent requests
    don't share history.

    narration=True (default) streams tool calls and intermediate steps as a
    live <think> block. Set narration=False to disable.
    """
    try:
        import uvicorn
    except ImportError:
        raise ImportError("uvicorn is required. Install with: uv add 'nori[server]'")

    app = make_app(agent_factory, model_id=model_id, narration=narration)
    print(f"nori chatbot listening on http://{host}:{port}/v1", flush=True)
    uvicorn.run(app, host=host, port=port)
