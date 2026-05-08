import subprocess
import sys

from nori.tool import tool


@tool
def CodeRunner(code: str) -> str:
    """Execute a Python 3 snippet and return its stdout."""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return f"[error]\n{result.stderr}"
    return result.stdout
