import os
import re
import subprocess
from contextvars import ContextVar

from nori.tool import tool
from nori.tools.base import ToolResult

# When set, Bash is sandboxed to this directory. Absolute paths outside it are rejected.
_bash_sandbox_dir: ContextVar[str | None] = ContextVar("nori_bash_sandbox_dir", default=None)

_ABS_PATH_RE = re.compile(r'(?<![.\w])(\/[^\s\'\";|&><(){}$`\\]+)')


def _check_sandbox(command: str, sandbox: str) -> str | None:
    """Return an error message if command references a path outside sandbox, else None."""
    for match in _ABS_PATH_RE.finditer(command):
        path = os.path.normpath(match.group(1))
        if not path.startswith(sandbox):
            return (
                f"Sandbox violation: '{match.group(1)}' is outside the allowed directory '{sandbox}'. "
                f"Use relative paths or paths within the project directory."
            )
    return None


@tool
def Bash(command: str) -> ToolResult:
    """Execute a shell command and return its output."""
    sandbox = _bash_sandbox_dir.get()
    if sandbox:
        error = _check_sandbox(command, sandbox)
        if error:
            return ToolResult(result=f"[error]\n{error}")
        proc = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=sandbox)
    else:
        proc = subprocess.run(command, shell=True, capture_output=True, text=True)
    output = proc.stdout
    if proc.stderr:
        output += f"\n[stderr]\n{proc.stderr}"
    if proc.returncode != 0:
        output = f"[exit code: {proc.returncode}]\n" + output
    return ToolResult(result=output)
