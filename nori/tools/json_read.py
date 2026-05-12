import json
from pathlib import Path

from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools._sandbox import sandbox_dir, check_path

_CHAR_CAP = 20_000


@tool
def JsonRead(path: str, path_expr: str = "", summarize: bool = False) -> ToolResult:
    """Read a JSON file. Use path_expr (JSONPath) to extract a subset, or
    summarize=True to return schema/shape info instead of full content.
    Summarize is useful for large files where you need structure before deciding
    what to extract."""
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

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return ToolResult(result=f"Invalid JSON in {path}: {e}")

    if path_expr:
        from jsonpath_ng import parse as jp_parse
        try:
            matches = [m.value for m in jp_parse(path_expr).find(data)]
        except Exception as e:
            return ToolResult(result=f"Invalid JSONPath expression: {e}")
        if not matches:
            return ToolResult(result=f"No matches for expression: {path_expr}")
        result = json.dumps(matches, indent=2)
        if len(result) > _CHAR_CAP:
            omitted = len(result) - _CHAR_CAP
            result = result[:_CHAR_CAP] + f"\n[truncated — {omitted:,} chars omitted]"
        return ToolResult(result=result)

    if summarize:
        return ToolResult(result=_summarize(data))

    result = json.dumps(data, indent=2)
    if len(result) > _CHAR_CAP:
        omitted = len(result) - _CHAR_CAP
        result = result[:_CHAR_CAP] + f"\n[truncated — {omitted:,} chars omitted]"
    return ToolResult(result=result)


def _summarize(data) -> str:
    if isinstance(data, list):
        header = f"Type: array[{len(data)} items]"
        if not data:
            return header
        sample = data[:5]
        schema_lines = _schema_lines(sample[0], indent=2)
        return header + f"\nItem schema (from first {min(5, len(data))}):\n" + "\n".join(schema_lines)
    elif isinstance(data, dict):
        lines = [f"Type: object[{len(data)} keys]"] + _schema_lines(data, indent=0)
        return "\n".join(lines)
    else:
        return f"Type: {_type_name(data)}\nValue: {data!r}"


def _schema_lines(obj, indent: int) -> list[str]:
    pad = " " * indent
    if isinstance(obj, dict):
        lines = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}{k}: {_type_name(v)}")
                lines.extend(_schema_lines(v, indent + 2))
            else:
                lines.append(f"{pad}{k}: {_type_name(v)}")
        return lines
    elif isinstance(obj, list):
        if obj:
            return _schema_lines(obj[0], indent + 2)
        return [f"{pad}(empty)"]
    else:
        return [f"{pad}{_type_name(obj)}"]


def _type_name(v) -> str:
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return f"array[{len(v)} items]"
    if isinstance(v, dict):
        return f"object[{len(v)} keys]"
    if v is None:
        return "null"
    return type(v).__name__
