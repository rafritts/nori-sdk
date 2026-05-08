import subprocess
from pathlib import Path

from nori.tool import tool


@tool
def FileSearch(path: str, pattern: str, content: str = "") -> str:
    """Find files under path matching a filename pattern or containing content."""
    root = Path(path)

    if content:
        result = subprocess.run(
            ["grep", "-rl", content, str(root)],
            capture_output=True,
            text=True,
        )
        matches = [l for l in result.stdout.splitlines() if l]
    else:
        matches = [str(p) for p in root.rglob(pattern) if p.is_file()]

    if not matches:
        return "No matches found."
    return "\n".join(matches)
