import subprocess

from nori.tool import tool
from nori.tools.base import ToolResult


@tool
def Bash(command: str) -> ToolResult:
    """Execute a shell command and return its output."""
    proc = subprocess.run(command, shell=True, capture_output=True, text=True)
    output = proc.stdout
    if proc.stderr:
        output += f"\n[stderr]\n{proc.stderr}"
    return ToolResult(result=output)
