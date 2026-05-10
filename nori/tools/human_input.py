import asyncio
import logging
import uuid

import nori.config as config
from nori.tool import tool
from nori.tools.base import ToolResult

logger = logging.getLogger("nori.hitl")


@tool
async def HumanInput(question: str, options: list = None) -> ToolResult:
    """Pause execution and ask the human operator a question. Use when you need approval,
    clarification, or a judgment call before proceeding. Provide a clear, specific question.
    Use options when the answer should be one of a fixed set of choices (advisory, not enforced)."""
    cfg = config.get_defaults().server
    request_id = uuid.uuid4().hex[:8]

    if cfg.enabled:
        from nori import server as _server
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        agent_name = _server._agent_name_var.get()
        _server.register_pending(request_id, future, agent_name, question, options or [])
        logger.info(
            "[nori] waiting for human input — POST http://%s:%d/hitl/%s/respond",
            cfg.host, cfg.port, request_id,
        )
        try:
            response = await future
        finally:
            _server.unregister_pending(request_id)
    else:
        lines = [
            "",
            "━" * 44,
            f"  Question: {question}",
        ]
        if options:
            lines.append("  Options: " + "  ".join(f"[{o}]" for o in options))
        lines.append("━" * 44)
        print("\n".join(lines))
        response = await asyncio.to_thread(input, "Your response: ")

    return ToolResult(result=response)
