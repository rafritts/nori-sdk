import json
import logging
import os
from contextvars import ContextVar
from typing import TYPE_CHECKING

from nori.enums import Propagation, ScratchpadUsage

logger = logging.getLogger("nori.scratchpad")

if TYPE_CHECKING:
    from pydantic import BaseModel

_scratchpad_var: ContextVar["Scratchpad | None"] = ContextVar("nori_scratchpad", default=None)

_USAGE_PROMPTS = {
    ScratchpadUsage.REQUIRED: (
        "You have access to a shared scratchpad. It is your primary coordination mechanism — "
        "write your findings to it and read from it before producing output. "
        "Treat it as required, not optional."
    ),
    ScratchpadUsage.SELECTIVE: (
        "You have access to a shared scratchpad. Only write to it if the information is "
        "critical for other agents. Do not write verbose summaries, intermediate steps, "
        "or anything a downstream agent could derive itself. Keep it signal, not noise."
    ),
}


class Scratchpad:
    def __init__(
        self,
        schema: "type[BaseModel] | None" = None,
        propagate: Propagation | None = None,
        usage: ScratchpadUsage | None = None,
        audit: bool = True,
        audit_path: str | None = None,
    ):
        self._schema_class = schema
        self._instance = schema() if schema else None
        self._store: dict[str, str] = {}
        self.propagate: Propagation = Propagation.ALWAYS if propagate is None else propagate
        self.usage: ScratchpadUsage = ScratchpadUsage.REQUIRED if usage is None else usage
        self.audit: bool = audit
        self.audit_path: str | None = audit_path

    @property
    def is_typed(self) -> bool:
        return self._instance is not None

    def read(self, key: str) -> str:
        if self._instance is not None:
            fields = self._schema_class.model_fields
            if key not in fields:
                return f"Field '{key}' not found. Available fields: {list(fields.keys())}"
            val = getattr(self._instance, key)
            return str(val) if val is not None else "(empty)"
        val = self._store.get(key)
        if val is None:
            keys = list(self._store.keys())
            return f"Key '{key}' not found." + (f" Available keys: {keys}" if keys else " Scratchpad is empty.")
        return val

    def write(self, key: str, value: str) -> str:
        if self._instance is not None:
            fields = self._schema_class.model_fields
            if key not in fields:
                return f"Field '{key}' not found. Available fields: {list(fields.keys())}"
            try:
                self._instance = self._instance.model_copy(update={key: value})
                return f"Written to '{key}'."
            except Exception as e:
                return f"Validation error writing '{key}': {e}"
        self._store[key] = value
        return f"Written to '{key}'."

    def usage_prompt(self) -> str:
        if self.usage is None:
            return ""
        return _USAGE_PROMPTS.get(self.usage, "")

    def schema_prompt(self) -> str:
        """Current scratchpad state for system prompt injection."""
        if self._instance is not None:
            lines = ["Scratchpad schema and current values (use field names with ScratchpadRead/ScratchpadWrite):"]
            for name in self._schema_class.model_fields:
                val = getattr(self._instance, name)
                lines.append(f"  - {name}: {json.dumps(str(val))}")
            return "\n".join(lines)
        if self._store:
            return "Scratchpad contents:\n" + json.dumps(self._store, indent=2)
        return "Scratchpad is empty."

    def dump_audit(self, agent_name: str) -> None:
        """Log and/or write final scratchpad state. Called by Agent.run() on exit."""
        if not self.audit and self.audit_path is None:
            return
        if self._instance is not None:
            data = self._instance.model_dump()
        else:
            data = dict(self._store)
        if self.audit:
            logger.info("scratchpad agent=%s\n%s", agent_name, json.dumps(data, indent=2))
        if self.audit_path is not None:
            os.makedirs(os.path.dirname(self.audit_path) or ".", exist_ok=True)
            with open(self.audit_path, "w") as f:
                json.dump({"agent": agent_name, "scratchpad": data}, f, indent=2)


def _make_owner_tools(pad: "Scratchpad"):
    """Create closure-based ScratchpadRead/Write tools that bypass the ContextVar.
    Used for the agent that owns the scratchpad."""
    from nori.tool import tool
    from nori.tools.base import ToolResult

    @tool
    async def ScratchpadRead(key: str) -> ToolResult:
        """Read a value from the scratchpad by key or field name."""
        return ToolResult(result=pad.read(key))

    @tool
    async def ScratchpadWrite(key: str, value: str) -> ToolResult:
        """Write a value to the scratchpad. In typed scratchpads, key must be a valid field name."""
        return ToolResult(result=pad.write(key, value))

    return ScratchpadRead, ScratchpadWrite


def _make_propagate_tool(pad: "Scratchpad"):
    """Create a ScratchpadPropagate tool that enables ContextVar-based access for sub-agents."""
    from nori.tool import tool

    @tool
    async def ScratchpadPropagate() -> str:
        """Enable scratchpad access for sub-agents spawned from this point forward."""
        _scratchpad_var.set(pad)
        return "Scratchpad propagation enabled. Sub-agents with ScratchpadRead/ScratchpadWrite can now access it."

    return ScratchpadPropagate
