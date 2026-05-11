import subprocess
from pathlib import Path

from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools._sandbox import sandbox_dir, check_path


@tool
def FileSearch(path: str, pattern: str, content: str = "") -> ToolResult:
    """Find files under path matching a filename pattern or containing content."""
    allowed = sandbox_dir.get()
    if allowed:
        error = check_path(path, allowed)
        if error:
            return ToolResult(result=f"[error]\n{error}")
    root = Path(path)

    if content:
        proc = subprocess.run(
            ["grep", "-rl", content, str(root)],
            capture_output=True,
            text=True,
        )
        matches = [line for line in proc.stdout.splitlines() if line]
    else:
        matches = [str(p) for p in root.rglob(pattern) if p.is_file()]

    result = "No matches found." if not matches else "\n".join(matches)
    return ToolResult(result=result)
