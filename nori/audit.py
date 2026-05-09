import json
from datetime import datetime, timezone


class AuditLogger:
    """
    Structured JSON-lines audit stream for a Nori agent run.

    Captures every agent start/end, tool call, and tool result as a
    discrete JSON object — one per line — suitable for ingestion by
    Splunk, Datadog, or any log aggregator.

    Usage:
        from nori.audit import AuditLogger
        agent.auditor = AuditLogger("myagent.audit.log")
    """

    def __init__(self, path: str) -> None:
        self._file = open(path, "a", buffering=1)

    def _write(self, event: str, **fields) -> None:
        record = {
            "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "event": event,
            **fields,
        }
        self._file.write(json.dumps(record) + "\n")

    def agent_start(self, agent: str, prompt: str, *, trace_id: str, span_id: str, parent_span_id: str | None) -> None:
        self._write(
            "agent_start",
            trace_id=trace_id, span_id=span_id, parent_span_id=parent_span_id,
            agent=agent, prompt=prompt,
        )

    def agent_end(self, agent: str, result: str, turns: int, cost: float, *, trace_id: str, span_id: str, parent_span_id: str | None) -> None:
        self._write(
            "agent_end",
            trace_id=trace_id, span_id=span_id, parent_span_id=parent_span_id,
            agent=agent, result=result, turns=turns, cost=cost,
        )

    def tool_call(self, agent: str, name: str, args: dict, *, trace_id: str, span_id: str, parent_span_id: str | None, call_id: str) -> None:
        self._write(
            "tool_call",
            trace_id=trace_id, span_id=span_id, parent_span_id=parent_span_id, call_id=call_id,
            agent=agent, name=name, args=args,
        )

    def tool_result(self, agent: str, name: str, result: str, *, trace_id: str, span_id: str, parent_span_id: str | None, call_id: str) -> None:
        self._write(
            "tool_result",
            trace_id=trace_id, span_id=span_id, parent_span_id=parent_span_id, call_id=call_id,
            agent=agent, name=name, result=result,
        )

    def tool_error(self, agent: str, name: str, error: str, *, trace_id: str, span_id: str, parent_span_id: str | None, call_id: str) -> None:
        self._write(
            "tool_error",
            trace_id=trace_id, span_id=span_id, parent_span_id=parent_span_id, call_id=call_id,
            agent=agent, name=name, error=error,
        )

    def close(self) -> None:
        self._file.close()
