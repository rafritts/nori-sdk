from pathlib import Path

from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools._sandbox import sandbox_dir, check_path


@tool
def FileWrite(path: str, content: str) -> ToolResult:
    """Write content to a file, creating it (and any missing parent directories)
    or overwriting it entirely. For partial edits to existing files, use FileEdit."""
    allowed = sandbox_dir.get()
    if allowed:
        error = check_path(path, allowed)
        if error:
            return ToolResult(result=f"[error]\n{error}")

    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(content)
    return ToolResult(result=f"Wrote {len(content.encode()):,} bytes to {path}")
