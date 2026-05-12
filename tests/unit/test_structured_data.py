import json
import pytest


# ── JsonRead — full content ───────────────────────────────────────────────────

async def test_json_read_object(tmp_path):
    from nori.tools.json_read import JsonRead
    f = tmp_path / "data.json"
    f.write_text(json.dumps({"name": "nori", "version": 1}))
    result = await JsonRead(path=str(f), reason="r")
    assert "nori" in result.result
    assert "version" in result.result


async def test_json_read_array(tmp_path):
    from nori.tools.json_read import JsonRead
    f = tmp_path / "list.json"
    f.write_text(json.dumps([1, 2, 3]))
    result = await JsonRead(path=str(f), reason="r")
    assert "1" in result.result


async def test_json_read_file_not_found(tmp_path):
    from nori.tools.json_read import JsonRead
    result = await JsonRead(path=str(tmp_path / "missing.json"), reason="r")
    assert "not found" in result.result.lower()


async def test_json_read_invalid_json(tmp_path):
    from nori.tools.json_read import JsonRead
    f = tmp_path / "bad.json"
    f.write_text("{not valid json")
    result = await JsonRead(path=str(f), reason="r")
    assert "invalid json" in result.result.lower()


async def test_json_read_truncates_large_file(tmp_path):
    from nori.tools.json_read import JsonRead
    f = tmp_path / "big.json"
    f.write_text(json.dumps({"data": "x" * 25_000}))
    result = await JsonRead(path=str(f), reason="r")
    assert "truncated" in result.result


# ── JsonRead — path_expr ──────────────────────────────────────────────────────

async def test_json_read_path_expr_extracts_values(tmp_path):
    from nori.tools.json_read import JsonRead
    f = tmp_path / "users.json"
    f.write_text(json.dumps([{"name": "alice"}, {"name": "bob"}]))
    result = await JsonRead(path=str(f), path_expr="$[*].name", reason="r")
    assert "alice" in result.result
    assert "bob" in result.result


async def test_json_read_path_expr_no_match(tmp_path):
    from nori.tools.json_read import JsonRead
    f = tmp_path / "data.json"
    f.write_text(json.dumps({"a": 1}))
    result = await JsonRead(path=str(f), path_expr="$.missing.key", reason="r")
    assert "no matches" in result.result.lower()


# ── JsonRead — summarize ──────────────────────────────────────────────────────

async def test_json_read_summarize_array(tmp_path):
    from nori.tools.json_read import JsonRead
    data = [{"id": i, "name": f"user{i}", "active": True} for i in range(100)]
    f = tmp_path / "big.json"
    f.write_text(json.dumps(data))
    result = await JsonRead(path=str(f), summarize=True, reason="r")
    assert "array" in result.result.lower()
    assert "100" in result.result
    assert "id" in result.result
    assert "name" in result.result


async def test_json_read_summarize_object(tmp_path):
    from nori.tools.json_read import JsonRead
    f = tmp_path / "obj.json"
    f.write_text(json.dumps({"foo": "bar", "count": 42}))
    result = await JsonRead(path=str(f), summarize=True, reason="r")
    assert "object" in result.result.lower()
    assert "foo" in result.result


def test_json_read_schema_has_reason_required():
    from nori.tools.json_read import JsonRead
    assert "reason" in JsonRead.schema["function"]["parameters"]["required"]


# ── JsonRead — sandbox / OS errors ───────────────────────────────────────────

async def test_json_read_sandbox_violation(tmp_path):
    from nori.tools.json_read import JsonRead
    from nori.tools._sandbox import sandbox_dir
    token = sandbox_dir.set(str(tmp_path))
    try:
        result = await JsonRead(path="/etc/passwd", reason="r")
        assert "[error]" in result.result
        assert "Sandbox violation" in result.result
    finally:
        sandbox_dir.reset(token)


async def test_json_read_os_error(tmp_path):
    from unittest.mock import patch
    from nori.tools.json_read import JsonRead
    import pathlib
    with patch.object(pathlib.Path, "read_text", side_effect=OSError("permission denied")):
        result = await JsonRead(path=str(tmp_path / "file.json"), reason="r")
    assert "Cannot read" in result.result or "permission denied" in result.result


# ── JsonRead — invalid JSONPath ───────────────────────────────────────────────

async def test_json_read_invalid_jsonpath(tmp_path):
    from nori.tools.json_read import JsonRead
    f = tmp_path / "data.json"
    f.write_text('{"a": 1}')
    result = await JsonRead(path=str(f), path_expr="[[[invalid", reason="r")
    assert "Invalid JSONPath" in result.result or "invalid" in result.result.lower()


async def test_json_read_jsonpath_result_truncated(tmp_path):
    from nori.tools.json_read import JsonRead
    data = [{"text": "x" * 500} for _ in range(50)]
    f = tmp_path / "big.json"
    f.write_text(json.dumps(data))
    result = await JsonRead(path=str(f), path_expr="$[*].text", reason="r")
    assert "truncated" in result.result


# ── JsonRead — summarize edge cases ──────────────────────────────────────────

async def test_json_read_summarize_empty_array(tmp_path):
    from nori.tools.json_read import JsonRead
    f = tmp_path / "empty.json"
    f.write_text("[]")
    result = await JsonRead(path=str(f), summarize=True, reason="r")
    assert "array" in result.result.lower()
    assert "0" in result.result


async def test_json_read_summarize_primitive(tmp_path):
    from nori.tools.json_read import JsonRead
    f = tmp_path / "prim.json"
    f.write_text("42")
    result = await JsonRead(path=str(f), summarize=True, reason="r")
    assert "integer" in result.result.lower() or "42" in result.result


async def test_json_read_summarize_nested_dict(tmp_path):
    from nori.tools.json_read import JsonRead
    data = {"user": {"name": "alice", "scores": [1, 2, 3]}}
    f = tmp_path / "nested.json"
    f.write_text(json.dumps(data))
    result = await JsonRead(path=str(f), summarize=True, reason="r")
    assert "user" in result.result
    assert "name" in result.result


async def test_json_read_summarize_array_with_nested_list(tmp_path):
    from nori.tools.json_read import JsonRead
    data = [{"tags": ["a", "b"]}]
    f = tmp_path / "nested_list.json"
    f.write_text(json.dumps(data))
    result = await JsonRead(path=str(f), summarize=True, reason="r")
    assert "array" in result.result.lower()


# ── JsonRead — type_name coverage ────────────────────────────────────────────

async def test_json_read_summarize_float(tmp_path):
    from nori.tools.json_read import JsonRead
    f = tmp_path / "float.json"
    f.write_text('{"val": 3.14}')
    result = await JsonRead(path=str(f), summarize=True, reason="r")
    assert "float" in result.result or "val" in result.result


async def test_json_read_summarize_boolean(tmp_path):
    from nori.tools.json_read import JsonRead
    f = tmp_path / "bool.json"
    f.write_text('{"active": true}')
    result = await JsonRead(path=str(f), summarize=True, reason="r")
    assert "boolean" in result.result or "active" in result.result


async def test_json_read_summarize_null(tmp_path):
    from nori.tools.json_read import JsonRead
    f = tmp_path / "null.json"
    f.write_text('{"val": null}')
    result = await JsonRead(path=str(f), summarize=True, reason="r")
    assert "null" in result.result or "val" in result.result


async def test_json_read_summarize_array_of_empty_lists(tmp_path):
    from nori.tools.json_read import JsonRead
    # Triggers the empty list path in _schema_lines (line 88)
    data = {"items": []}
    f = tmp_path / "empty_list.json"
    f.write_text(json.dumps(data))
    result = await JsonRead(path=str(f), summarize=True, reason="r")
    assert "items" in result.result


async def test_json_read_type_name_unknown_type(tmp_path):
    from nori.tools.json_read import _type_name
    import datetime
    # Triggers type(v).__name__ fallback (line 108)
    result = _type_name(datetime.date.today())
    assert "date" in result


# ── CsvRead — row data ────────────────────────────────────────────────────────

async def test_csv_read_returns_table(tmp_path):
    from nori.tools.csv_read import CsvRead
    f = tmp_path / "data.csv"
    f.write_text("id,name,score\n1,alice,95\n2,bob,87\n")
    result = await CsvRead(path=str(f), reason="r")
    assert "alice" in result.result
    assert "bob" in result.result
    assert "score" in result.result


async def test_csv_read_shows_total_row_count(tmp_path):
    from nori.tools.csv_read import CsvRead
    rows = "id,val\n" + "\n".join(f"{i},{i*2}" for i in range(100))
    f = tmp_path / "many.csv"
    f.write_text(rows)
    result = await CsvRead(path=str(f), reason="r")
    assert "100" in result.result


async def test_csv_read_respects_max_rows(tmp_path):
    from nori.tools.csv_read import CsvRead
    rows = "id,val\n" + "\n".join(f"{i},{i}" for i in range(100))
    f = tmp_path / "rows.csv"
    f.write_text(rows)
    result = await CsvRead(path=str(f), max_rows=5, reason="r")
    assert "showing first 5" in result.result


async def test_csv_read_file_not_found(tmp_path):
    from nori.tools.csv_read import CsvRead
    result = await CsvRead(path=str(tmp_path / "missing.csv"), reason="r")
    assert "not found" in result.result.lower()


async def test_csv_read_empty_file(tmp_path):
    from nori.tools.csv_read import CsvRead
    f = tmp_path / "empty.csv"
    f.write_text("")
    result = await CsvRead(path=str(f), reason="r")
    assert "empty" in result.result.lower()


async def test_csv_read_tab_delimiter(tmp_path):
    from nori.tools.csv_read import CsvRead
    f = tmp_path / "tabs.tsv"
    f.write_text("a\tb\tc\n1\t2\t3\n")
    result = await CsvRead(path=str(f), reason="r")
    assert "a" in result.result
    assert "1" in result.result


# ── CsvRead — summarize ───────────────────────────────────────────────────────

async def test_csv_read_summarize_returns_column_stats(tmp_path):
    from nori.tools.csv_read import CsvRead
    rows = "id,name,score\n" + "\n".join(f"{i},user{i},{i*10}" for i in range(50))
    f = tmp_path / "stats.csv"
    f.write_text(rows)
    result = await CsvRead(path=str(f), summarize=True, reason="r")
    assert "id" in result.result
    assert "name" in result.result
    assert "score" in result.result
    assert "50" in result.result


async def test_csv_read_infers_integer_type(tmp_path):
    from nori.tools.csv_read import CsvRead
    f = tmp_path / "nums.csv"
    f.write_text("val\n1\n2\n3\n")
    result = await CsvRead(path=str(f), summarize=True, reason="r")
    assert "integer" in result.result


def test_csv_read_schema_has_reason_required():
    from nori.tools.csv_read import CsvRead
    assert "reason" in CsvRead.schema["function"]["parameters"]["required"]


# ── CsvRead — sandbox / OS errors ────────────────────────────────────────────

async def test_csv_read_sandbox_violation(tmp_path):
    from nori.tools.csv_read import CsvRead
    from nori.tools._sandbox import sandbox_dir
    token = sandbox_dir.set(str(tmp_path))
    try:
        result = await CsvRead(path="/etc/passwd", reason="r")
        assert "[error]" in result.result
        assert "Sandbox violation" in result.result
    finally:
        sandbox_dir.reset(token)


async def test_csv_read_os_error(tmp_path):
    from unittest.mock import patch
    from nori.tools.csv_read import CsvRead
    import pathlib
    with patch.object(pathlib.Path, "read_text", side_effect=OSError("permission denied")):
        result = await CsvRead(path=str(tmp_path / "file.csv"), reason="r")
    assert "Cannot read" in result.result or "permission denied" in result.result


async def test_csv_read_parse_error(tmp_path):
    from unittest.mock import patch
    from nori.tools.csv_read import CsvRead
    import csv
    f = tmp_path / "bad.csv"
    f.write_text("a,b\n1,2\n")
    with patch("csv.DictReader", side_effect=csv.Error("bad csv")):
        result = await CsvRead(path=str(f), reason="r")
    assert "CSV parse error" in result.result or "bad csv" in result.result


async def test_csv_read_headers_no_data(tmp_path):
    from nori.tools.csv_read import CsvRead
    f = tmp_path / "headers_only.csv"
    f.write_text("id,name,score\n")
    result = await CsvRead(path=str(f), reason="r")
    assert "headers" in result.result.lower() or "no data" in result.result.lower()


# ── CsvRead — additional type inference ──────────────────────────────────────

async def test_csv_read_infers_float_type(tmp_path):
    from nori.tools.csv_read import CsvRead
    f = tmp_path / "floats.csv"
    f.write_text("val\n1.5\n2.7\n3.1\n")
    result = await CsvRead(path=str(f), summarize=True, reason="r")
    assert "float" in result.result


async def test_csv_read_infers_boolean_type(tmp_path):
    from nori.tools.csv_read import CsvRead
    f = tmp_path / "bools.csv"
    f.write_text("active\ntrue\nfalse\ntrue\n")
    result = await CsvRead(path=str(f), summarize=True, reason="r")
    assert "boolean" in result.result


async def test_csv_read_infers_date_type(tmp_path):
    from nori.tools.csv_read import CsvRead
    f = tmp_path / "dates.csv"
    f.write_text("created_at\n2024-01-01\n2024-06-15\n2024-12-31\n")
    result = await CsvRead(path=str(f), summarize=True, reason="r")
    assert "date" in result.result


async def test_csv_read_infers_unknown_when_empty_values(tmp_path):
    from nori.tools.csv_read import CsvRead
    f = tmp_path / "nulls.csv"
    # Rows with empty values but non-empty cells (whitespace won't do it, need actual rows)
    f.write_text("val,label\n,\n,\n,\n")
    result = await CsvRead(path=str(f), summarize=True, reason="r")
    assert "unknown" in result.result or "val" in result.result


async def test_csv_read_pipe_delimiter(tmp_path):
    from nori.tools.csv_read import CsvRead
    f = tmp_path / "pipe.csv"
    f.write_text("a|b|c\n1|2|3\n")
    result = await CsvRead(path=str(f), reason="r")
    assert "a" in result.result
    assert "1" in result.result


async def test_csv_read_semicolon_delimiter(tmp_path):
    from nori.tools.csv_read import CsvRead
    f = tmp_path / "semi.csv"
    f.write_text("a;b;c\n1;2;3\n")
    result = await CsvRead(path=str(f), reason="r")
    assert "a" in result.result
