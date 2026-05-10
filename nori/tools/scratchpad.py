"""ContextVar-based scratchpad tools for sub-agents."""

from nori.scratchpad import _scratchpad_var
from nori.tool import tool
from nori.tools.base import ToolResult


@tool
async def ScratchpadRead(key: str) -> ToolResult:
    """Read a value from the shared scratchpad by key or field name."""
    pad = _scratchpad_var.get()
    if pad is None:
        return ToolResult(result="No scratchpad available in this context.")
    return ToolResult(result=pad.read(key))


@tool
async def ScratchpadWrite(key: str, value: str) -> ToolResult:
    """Write a value to the shared scratchpad. In typed scratchpads, key must be a valid field name."""
    pad = _scratchpad_var.get()
    if pad is None:
        return ToolResult(result="No scratchpad available in this context.")
    return ToolResult(result=pad.write(key, value))
