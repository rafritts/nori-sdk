import asyncio
import logging
import uuid

import nori.config as config
from nori import durable
from nori.tool import tool
from nori.tools.base import ToolResult

logger = logging.getLogger("nori.hitl")


def _agent_name() -> str:
    try:
        from nori import server as _server
        return _server._agent_name_var.get()
    except Exception:
        return "unknown"


def _remember_response(journal, run_id, request_id, response: str) -> None:
    """Commit the answer before the caller observes it."""
    if journal is None or not run_id or not request_id:
        return
    journal.save_hitl_response(request_id, response)


@tool
async def HumanInput(question: str, options: list = None, timeout_seconds: int = None) -> ToolResult:
    """Pause execution and ask the human operator a question. Use when you need approval,
    clarification, or a judgment call before proceeding. Provide a clear, specific question.
    Use options when the answer should be one of a fixed set of choices (advisory, not enforced).
    Use timeout_seconds to avoid blocking forever if no response arrives."""
    cfg = config.get_defaults().server
    journal = durable.get_journal()
    run_id = durable.current_run_id()
    tool_call_id = durable.current_tool_call_id()
    options = options or []

    request_id = None
    if journal is not None and run_id and tool_call_id:
        row = journal.get_hitl(run_id, tool_call_id)
        if row is not None and row["response"] is not None:
            return ToolResult(result=row["response"])
        if row is not None:
            request_id = row["request_id"]
        else:
            request_id = uuid.uuid4().hex[:8]
            journal.insert_hitl(
                request_id, run_id, tool_call_id, _agent_name(), question, options,
            )
    else:
        request_id = uuid.uuid4().hex[:8]

    async def _get_response() -> str:
        if cfg.enabled:
            from nori import server as _server
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            _server.register_pending(request_id, future, _agent_name(), question, options)
            if journal is not None and run_id:
                journal.set_status(run_id, "waiting")
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
        message = f"[No response received within {timeout_seconds}s. Proceeding without human input.]"
        _remember_response(journal, run_id, request_id, message)
        return ToolResult(result=message)

    _remember_response(journal, run_id, request_id, response)
    return ToolResult(result=response)
