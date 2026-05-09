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

    def agent_start(self, agent: str, prompt: str) -> None:
        self._write("agent_start", agent=agent, prompt=prompt)

    def agent_end(self, agent: str, result: str, turns: int, cost: float) -> None:
        self._write("agent_end", agent=agent, result=result, turns=turns, cost=cost)

    def tool_call(self, agent: str, name: str, args: dict) -> None:
        self._write("tool_call", agent=agent, name=name, args=args)

    def tool_result(self, agent: str, name: str, result: str) -> None:
        self._write("tool_result", agent=agent, name=name, result=result)

    def tool_error(self, agent: str, name: str, error: str) -> None:
        self._write("tool_error", agent=agent, name=name, error=error)

    def close(self) -> None:
        self._file.close()
