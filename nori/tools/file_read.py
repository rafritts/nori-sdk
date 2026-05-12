from pathlib import Path

from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools._sandbox import sandbox_dir, check_path

_CHAR_CAP = 50_000


@tool
def FileRead(path: str, start_line: int = None, end_line: int = None) -> ToolResult:
    """Read a file and return its contents. Use start_line and end_line (1-indexed,
    inclusive) to read a specific range — output will include line numbers to aid
    precise FileEdit calls. Without a range, returns the full file."""
    allowed = sandbox_dir.get()
    if allowed:
        error = check_path(path, allowed)
        if error:
            return ToolResult(result=f"[error]\n{error}")

    try:
        text = Path(path).read_text()
    except FileNotFoundError:
        return ToolResult(result=f"File not found: {path}")
    except OSError as e:
        return ToolResult(result=f"Cannot read {path}: {e}")

    if start_line is not None or end_line is not None:
        lines = text.splitlines(keepends=True)
        total = len(lines)
        lo = (start_line - 1) if start_line is not None else 0
        hi = end_line if end_line is not None else total
        lo = max(0, lo)
        hi = min(total, hi)
        slice_ = lines[lo:hi]
        numbered = "".join(f"{lo + i + 1:4} | {line}" for i, line in enumerate(slice_))
        result = numbered
    else:
        result = text

    if len(result) > _CHAR_CAP:
        omitted = len(result) - _CHAR_CAP
        result = result[:_CHAR_CAP] + f"\n[truncated — {omitted:,} chars omitted]"

    return ToolResult(result=result)
