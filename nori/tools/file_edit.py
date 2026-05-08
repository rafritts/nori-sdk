from pathlib import Path

from nori.tool import tool


@tool
def FileEdit(path: str, old_content: str, new_content: str) -> str:
    """Replace old_content with new_content in the file at path."""
    file = Path(path)
    text = file.read_text()
    if old_content not in text:
        raise ValueError(f"old_content not found in {path}")
    file.write_text(text.replace(old_content, new_content, 1))
    return f"Edited {path}"
