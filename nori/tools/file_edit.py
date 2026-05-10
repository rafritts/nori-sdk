from pathlib import Path

from nori.tool import tool
from nori.tools.base import ToolResult


@tool
def FileEdit(path: str, old_content: str, new_content: str) -> ToolResult:
    """Replace old_content with new_content in the file at path."""
    file = Path(path)
    try:
        text = file.read_text()
    except FileNotFoundError:
        return ToolResult(result=f"File not found: {path}")
    if old_content not in text:
        raise ValueError(f"old_content not found in {path}")
    file.write_text(text.replace(old_content, new_content, 1))
    return ToolResult(result=f"Edited {path}")
