import asyncio
import logging
import uuid

import nori.config as config
from nori.tool import tool
from nori.tools.base import ToolResult

logger = logging.getLogger("nori.hitl")


@tool
async def HumanInput(question: str, options: list = None, timeout_seconds: int = None) -> ToolResult:
    """Pause execution and ask the human operator a question. Use when you need approval,
    clarification, or a judgment call before proceeding. Provide a clear, specific question.
    Use options when the answer should be one of a fixed set of choices (advisory, not enforced).
    Use timeout_seconds to avoid blocking forever if no response arrives."""
    cfg = config.get_defaults().server
    request_id = uuid.uuid4().hex[:8]

    async def _get_response() -> str:
        if cfg.enabled:
            from nori import server as _server
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            agent_name = _server._agent_name_var.get()
            _server.register_pending(request_id, future, agent_name, question, options or [])
            logger.info(
                "[nori] waiting for human input — POST http://%s:%d/hitl/%s/respond "
                "(header 'X-Nori-Token: %s')",
                cfg.host, cfg.port, request_id, cfg.token,
            )
            try:
                return await future
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
            return await asyncio.to_thread(input, "Your response: ")

    try:
        response = await asyncio.wait_for(_get_response(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        if cfg.enabled:
            from nori import server as _server
            _server.unregister_pending(request_id)
        return ToolResult(result=f"[No response received within {timeout_seconds}s. Proceeding without human input.]")

    return ToolResult(result=response)
