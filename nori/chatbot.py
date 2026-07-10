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
import re
import time
import uuid
from typing import AsyncGenerator, Callable

logger = logging.getLogger("nori.chatbot")

_KEEPALIVE_INTERVAL = 5  # seconds between SSE keepalive pings
_IMG_MD = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def _stream_filter_extra(base: str, filtered: str) -> str:
    """Content to stream after per-turn text was already sent via on_assistant_content.

    Prefer a pure suffix when the filter only appends (typical image inject).
    If the filter rewrites/reorders (e.g. model put image markdown first), only
    emit image markdown that was not already in the streamed base — never the
    full filtered body, which would duplicate prose + images in the client.
    """
    if not filtered:
        return ""
    if not base:
        return filtered
    if filtered.startswith(base):
        return filtered[len(base) :]
    base_urls = {m.group(2) for m in _IMG_MD.finditer(base)}
    new_imgs = [
        m.group(0) for m in _IMG_MD.finditer(filtered) if m.group(2) not in base_urls
    ]
    return ("\n\n" + "\n\n".join(new_imgs)) if new_imgs else ""


def make_app(
    agent_factory: Callable,
    model_id: str = "nori",
    narration: bool = True,
    static_dirs: dict[str, str] | None = None,
    keepalive: bool = False,
    response_filter: Callable[[str, list], str] | None = None,
) -> "FastAPI":
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel, ConfigDict

    import os
    app = FastAPI(title="nori-chatbot", docs_url=None, redoc_url=None)

    if static_dirs:
        from fastapi.staticfiles import StaticFiles
        for url_path, fs_path in static_dirs.items():
            os.makedirs(fs_path, exist_ok=True)
            app.mount(url_path, StaticFiles(directory=fs_path), name=url_path.lstrip("/"))

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    class Message(BaseModel):
        role: str
        content: str

    # Core OpenAI-compat fields only. Any additional JSON keys are accepted and
    # stamped onto the agent for harness hooks (tool filters, apply_request_knobs).
    # Nori does not interpret product-specific knobs.
    _CHAT_CORE_FIELDS = frozenset({"model", "messages", "stream"})

    class ChatRequest(BaseModel):
        model_config = ConfigDict(extra="allow")

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
        cid = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())

        agent = agent_factory()
        # Generic: stamp non-core request fields onto the agent so harnesses can
        # read them in tool_args_filter / apply_request_knobs without nori knowing
        # product-specific names.
        for key, value in req.model_dump(exclude_none=True).items():
            if key not in _CHAT_CORE_FIELDS:
                setattr(agent, key, value)
        apply_knobs = getattr(agent, "apply_request_knobs", None)
        if callable(apply_knobs):
            apply_knobs(req)

        last_user_idx = max(
            (i for i, m in enumerate(req.messages) if m.role == "user"),
            default=None,
        )
        if last_user_idx is None:
            return {"error": "no user message in request"}

        for msg in req.messages[:last_user_idx]:
            agent._history.append({"role": msg.role, "content": msg.content})

        prompt = req.messages[last_user_idx].content

        if req.stream:
            queue: asyncio.Queue = asyncio.Queue()

            if narration:
                agent.narration = True
                def _on_narration(msg):
                    print(msg, flush=True)
                    queue.put_nowait(("narration", msg))
                agent.on_narration = _on_narration

            # Each turn's text block → visible message content as soon as it arrives.
            def _on_assistant_content(text: str):
                if text:
                    print(text, flush=True)
                    queue.put_nowait(("assistant", text))
            agent.on_assistant_content = _on_assistant_content

            async def _run():
                try:
                    result = await agent.run(prompt)
                    # Text was already pushed per-turn via on_assistant_content.
                    # Only push post-filter extras (e.g. injected image markdown).
                    extra = ""
                    if response_filter:
                        base = result or ""
                        filtered = response_filter(base, agent.tool_calls)
                        extra = _stream_filter_extra(base, filtered)
                    tc = agent.token_counts
                    logger.debug(
                        "chat cid=%s turns=%d tokens=%d cost=$%.4f",
                        cid, agent.turn_count, tc.get("total", tc["prompt"] + tc["completion"]), agent.cost,
                    )
                    queue.put_nowait(("done", extra))
                except Exception as e:
                    queue.put_nowait(("error", str(e)))

            asyncio.create_task(_run())

            return StreamingResponse(
                _stream_live(queue, cid, created, model_id, keepalive=keepalive),
                media_type="text/event-stream",
            )

        # Non-streaming path
        narration_lines: list[str] = []
        assistant_parts: list[str] = []
        if narration:
            agent.narration = True
            def _collect(msg):
                print(msg, flush=True)
                narration_lines.append(msg)
            agent.on_narration = _collect

        def _collect_assistant(text: str):
            if text:
                print(text, flush=True)
                assistant_parts.append(text)
        agent.on_assistant_content = _collect_assistant

        result = await agent.run(prompt)

        # Per-turn text already collected (including final turn) — don't double-append result.
        body_parts = [p.strip() for p in assistant_parts if p and p.strip()]
        if not body_parts and result and result.strip():
            body_parts.append(result.strip())
        body = "\n\n".join(body_parts)

        if response_filter:
            body = response_filter(body, agent.tool_calls)

        if narration_lines:
            body = f"<think>\n{chr(10).join(narration_lines)}\n</think>\n{body}"

        tc = agent.token_counts
        logger.debug(
            "chat cid=%s turns=%d tokens=%d cost=$%.4f",
            cid, agent.turn_count, tc.get("total", tc["prompt"] + tc["completion"]), agent.cost,
        )
        return _non_stream_response(
            body, cid, created, model_id,
            tc["prompt"], tc["completion"], tc.get("reasoning", 0),
        )

    return app


def _non_stream_response(
    content: str,
    cid: str,
    created: int,
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    reasoning_tokens: int = 0,
) -> dict:
    total = prompt_tokens + completion_tokens + reasoning_tokens
    usage: dict = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total,
    }
    if reasoning_tokens:
        usage["completion_tokens_details"] = {"reasoning_tokens": reasoning_tokens}
    return {
        "id": cid,
        "object": "chat.completion",
        "created": created,
        "model": model_id,
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ],
        "usage": usage,
    }


def _stream_text_chunks(cid: str, created: int, model_id: str, text: str) -> list[str]:
    """Split text into SSE chunks. Prefer paragraph-ish chunks over pure word drip for prose."""
    if not text:
        return []
    chunks: list[str] = []
    # Keep word-level drip for short strings; larger blocks stream by lines for readability.
    if len(text) < 80:
        words = text.split(" ")
        for i, word in enumerate(words):
            content = word if i == len(words) - 1 else word + " "
            chunks.append(_chunk(cid, created, model_id, {"content": content}))
        return chunks

    parts = text.split("\n")
    for i, part in enumerate(parts):
        piece = part if i == len(parts) - 1 else part + "\n"
        if piece:
            chunks.append(_chunk(cid, created, model_id, {"content": piece}))
    return chunks


async def _stream_live(queue: asyncio.Queue, cid: str, created: int, model_id: str, keepalive: bool = False) -> AsyncGenerator[str, None]:
    in_think = False
    sent_role = False

    def _open_message():
        nonlocal sent_role
        out = []
        if not sent_role:
            out.append(_chunk(cid, created, model_id, {"role": "assistant", "content": ""}))
            sent_role = True
        return out

    while True:
        try:
            type_, data = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_INTERVAL if keepalive else None)
        except asyncio.TimeoutError:
            yield ": keepalive\n\n"
            continue

        if type_ == "narration":
            for c in _open_message():
                yield c
            if not in_think:
                yield _chunk(cid, created, model_id, {"content": "<think>\n"})
                in_think = True
            yield _chunk(cid, created, model_id, {"content": data + "\n"})

        elif type_ == "assistant":
            # Close any open think block so mid-loop prose is real message content.
            for c in _open_message():
                yield c
            if in_think:
                yield _chunk(cid, created, model_id, {"content": "</think>\n"})
                in_think = False
            text = data if data.endswith("\n") else data + "\n\n"
            for c in _stream_text_chunks(cid, created, model_id, text):
                yield c

        elif type_ == "done":
            for c in _open_message():
                yield c
            if in_think:
                yield _chunk(cid, created, model_id, {"content": "</think>\n"})
                in_think = False
            for c in _stream_text_chunks(cid, created, model_id, data):
                yield c
            yield _chunk(cid, created, model_id, {}, finish_reason="stop")
            yield "data: [DONE]\n\n"
            break

        elif type_ == "error":
            for c in _open_message():
                yield c
            if in_think:
                yield _chunk(cid, created, model_id, {"content": "</think>\n"})
                in_think = False
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
    static_dirs: dict[str, str] | None = None,
    keepalive: bool = False,
    response_filter: Callable[[str, list], str] | None = None,
) -> None:
    """Start an OpenAI-compatible chat server backed by a nori Agent.

    agent_factory must be a zero-argument callable that returns a fresh Agent
    per request — required so each user gets clean state and concurrent requests
    don't share history.

    narration=True (default) streams tool calls and intermediate steps as a
    live <think> block. Each turn's assistant text is sent as message content as
    soon as that turn completes (before tools run). Set narration=False to
    disable the think channel.
    """
    try:
        import uvicorn
    except ImportError:
        raise ImportError("uvicorn is required. Install with: uv add 'nori[server]'")

    app = make_app(agent_factory, model_id=model_id, narration=narration, static_dirs=static_dirs, keepalive=keepalive, response_filter=response_filter)
    print(f"nori chatbot listening on http://{host}:{port}/v1", flush=True)
    uvicorn.run(app, host=host, port=port)
