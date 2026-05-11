import subprocess

from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools._sandbox import sandbox_dir, check_command


@tool
def Bash(command: str) -> ToolResult:
    """Execute a shell command and return its output."""
    allowed = sandbox_dir.get()
    if allowed:
        error = check_command(command, allowed)
        if error:
            return ToolResult(result=f"[error]\n{error}")
        proc = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=allowed)
    else:
        proc = subprocess.run(command, shell=True, capture_output=True, text=True)
    output = proc.stdout
    if proc.stderr:
        output += f"\n[stderr]\n{proc.stderr}"
    if proc.returncode != 0:
        output = f"[exit code: {proc.returncode}]\n" + output
    return ToolResult(result=output)
