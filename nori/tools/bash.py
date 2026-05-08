import subprocess

from nori.tool import tool


@tool
def Bash(command: str) -> str:
    """Execute a shell command and return its stdout and stderr."""
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
    )
    output = result.stdout
    if result.stderr:
        output += f"\n[stderr]\n{result.stderr}"
    return output
