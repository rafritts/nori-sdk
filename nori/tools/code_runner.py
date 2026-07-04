import subprocess
import sys

from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools._sandbox import sandbox_dir, check_command


@tool
def CodeRunner(code: str) -> ToolResult:
    """Execute a Python 3 snippet and return its stdout.

    Runs in a subprocess whose cwd is the sandbox dir, but the code is NOT
    otherwise confined — it has the full privileges of the host process. The
    path scan is a guardrail against accidental stray paths, not a security
    boundary. See docs/security.md.
    """
    allowed = sandbox_dir.get()
    if allowed:
        error = check_command(code, allowed)
        if error:
            return ToolResult(result=f"[error]\n{error}")
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=allowed)
    else:
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    result = f"[error]\n{proc.stderr}" if proc.returncode != 0 else proc.stdout
    return ToolResult(result=result)
