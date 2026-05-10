import subprocess
import sys

from nori.tool import tool
from nori.tools.base import ToolResult


@tool
def CodeRunner(code: str) -> ToolResult:
    """Execute a Python 3 snippet and return its stdout."""
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    result = f"[error]\n{proc.stderr}" if proc.returncode != 0 else proc.stdout
    return ToolResult(result=result)
