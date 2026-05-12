import csv
import io
from pathlib import Path

from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools._sandbox import sandbox_dir, check_path

_DEFAULT_MAX_ROWS = 50
_SAMPLE_SIZE = 5


@tool
def CsvRead(path: str, max_rows: int = _DEFAULT_MAX_ROWS, summarize: bool = False, delimiter: str = "") -> ToolResult:
    """Read a CSV file and return a markdown table (up to max_rows rows).
    Use summarize=True to return column statistics instead of row data — useful
    for large files. Leave delimiter empty for auto-detection."""
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

    if not text.strip():
        return ToolResult(result="File is empty.")

    delim = delimiter or _detect_delimiter(text)

    try:
        reader = csv.DictReader(io.StringIO(text), delimiter=delim)
        rows = list(reader)
    except csv.Error as e:
        return ToolResult(result=f"CSV parse error: {e}")

    if not rows:
        return ToolResult(result="File has headers but no data rows.")

    headers = list(rows[0].keys())
    total = len(rows)

    if summarize:
        return ToolResult(result=_summarize(headers, rows, total))

    shown = rows[:max_rows]
    table = _markdown_table(headers, shown)
    suffix = f"\nTotal rows: {total:,} (showing first {len(shown)})" if total > max_rows else f"\nTotal rows: {total:,}"
    return ToolResult(result=suffix.lstrip("\n") + "\n\n" + table)


def _detect_delimiter(text: str) -> str:
    first_line = text.splitlines()[0]
    for d in (",", "\t", ";", "|"):
        if d in first_line:
            return d
    return ","


def _markdown_table(headers: list[str], rows: list[dict]) -> str:
    col_widths = [max(len(h), max((len(str(r.get(h, ""))) for r in rows), default=0)) for h in headers]
    sep = "| " + " | ".join("-" * w for w in col_widths) + " |"
    header_row = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"
    data_rows = [
        "| " + " | ".join(str(r.get(h, "")).ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"
        for r in rows
    ]
    return "\n".join([header_row, sep] + data_rows)


def _summarize(headers: list[str], rows: list[dict], total: int) -> str:
    lines = [f"Total rows: {total:,}", f"Columns: {len(headers)}", ""]
    col_header = "| column | type | nulls | sample values |"
    col_sep =    "|--------|------|-------|---------------|"
    col_rows = []
    for h in headers:
        vals = [r.get(h, "") for r in rows]
        non_null = [v for v in vals if v not in ("", None)]
        nulls = total - len(non_null)
        inferred = _infer_type(non_null[:_SAMPLE_SIZE])
        sample = ", ".join(str(v) for v in non_null[:3])
        col_rows.append(f"| {h} | {inferred} | {nulls} | {sample} |")
    lines += [col_header, col_sep] + col_rows
    return "\n".join(lines)


def _infer_type(values: list) -> str:
    if not values:
        return "unknown"
    for type_name, check in [
        ("boolean", lambda v: v.lower() in ("true", "false", "1", "0", "yes", "no")),
        ("integer", lambda v: v.lstrip("-").isdigit()),
        ("float", _is_float),
        ("date", _is_date),
    ]:
        if all(check(str(v)) for v in values):
            return type_name
    return "string"


def _is_float(v: str) -> bool:
    try:
        float(v)
        return True
    except ValueError:
        return False


def _is_date(v: str) -> bool:
    import re
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}", v))
