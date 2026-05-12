from unittest.mock import MagicMock, patch

import pytest


# ── Bash ──────────────────────────────────────────────────────────────────────

async def test_bash_stdout_returned():
    from nori.tools.bash import Bash
    result = await Bash(command="echo hello", reason="test", summary="checked greeting")
    assert "hello" in result.result


async def test_bash_stderr_returned():
    from nori.tools.bash import Bash
    result = await Bash(command="echo err >&2", reason="test", summary="checked stderr")
    assert "err" in result.result


async def test_bash_summary_stripped_from_call():
    from nori.tools.bash import Bash
    # summary is a framework field — tool result has no summary attribute
    result = await Bash(command="echo hello", reason="test", summary="stripped by framework")
    assert not hasattr(result, "summary")


async def test_bash_reason_not_in_command():
    from nori.tools.bash import Bash
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="out", stderr="")
        await Bash(command="ls", reason="my secret reason")
        cmd = mock_run.call_args.args[0]
        assert "my secret reason" not in cmd


async def test_bash_schema_has_reason_required():
    from nori.tools.bash import Bash
    assert "reason" in Bash.schema["function"]["parameters"]["required"]


# ── FileEdit ──────────────────────────────────────────────────────────────────

async def test_file_edit_replaces_content(tmp_path):
    from nori.tools.file_edit import FileEdit
    f = tmp_path / "test.txt"
    f.write_text("hello world")
    await FileEdit(path=str(f), old_content="world", new_content="nori", reason="r")
    assert f.read_text() == "hello nori"


async def test_file_edit_missing_old_content_raises(tmp_path):
    from nori.tools.file_edit import FileEdit
    f = tmp_path / "test.txt"
    f.write_text("hello world")
    with pytest.raises(ValueError):
        await FileEdit(path=str(f), old_content="missing", new_content="x", reason="r")


async def test_file_edit_reason_not_written_to_file(tmp_path):
    from nori.tools.file_edit import FileEdit
    f = tmp_path / "test.txt"
    f.write_text("original content")
    await FileEdit(path=str(f), old_content="original", new_content="updated", reason="secret reason")
    assert "secret reason" not in f.read_text()


# ── FileSearch ────────────────────────────────────────────────────────────────

async def test_file_search_finds_by_name(tmp_path):
    from nori.tools.file_search import FileSearch
    (tmp_path / "foo.py").write_text("x")
    (tmp_path / "bar.txt").write_text("x")
    result = await FileSearch(path=str(tmp_path), pattern="*.py", reason="r")
    assert "foo.py" in result.result
    assert "bar.txt" not in result.result


async def test_file_search_finds_by_content(tmp_path):
    from nori.tools.file_search import FileSearch
    (tmp_path / "a.txt").write_text("hello nori world")
    (tmp_path / "b.txt").write_text("unrelated")
    result = await FileSearch(path=str(tmp_path), pattern="*", content="nori", reason="r")
    assert "a.txt" in result.result
    assert "b.txt" not in result.result


async def test_file_search_no_match_returns_empty(tmp_path):
    from nori.tools.file_search import FileSearch
    result = await FileSearch(path=str(tmp_path), pattern="*.xyz", reason="r")
    assert result.result == "No matches found."


# ── FileEdit — additional ─────────────────────────────────────────────────────

async def test_file_edit_file_not_found(tmp_path):
    from nori.tools.file_edit import FileEdit
    result = await FileEdit(path=str(tmp_path / "missing.txt"), old_content="x", new_content="y", reason="r")
    assert "not found" in result.result.lower()


async def test_file_read_os_error(tmp_path):
    from unittest.mock import patch
    from nori.tools.file_read import FileRead
    import pathlib
    with patch.object(pathlib.Path, "read_text", side_effect=OSError("permission denied")):
        result = await FileRead(path=str(tmp_path / "file.txt"), reason="r")
    assert "Cannot read" in result.result or "permission denied" in result.result


# ── FileSearch — additional ───────────────────────────────────────────────────

async def test_file_search_content_no_match(tmp_path):
    from nori.tools.file_search import FileSearch
    (tmp_path / "a.txt").write_text("unrelated content")
    result = await FileSearch(path=str(tmp_path), pattern="*", content="nonexistent", reason="r")
    assert result.result == "No matches found."


# ── ApiClient ─────────────────────────────────────────────────────────────────

async def test_api_client_invalid_headers_returns_error():
    from nori.tools.api_client import ApiClient
    result = await ApiClient(url="http://example.com", headers="not-json", reason="r")
    assert "[error]" in result.result
    assert "headers" in result.result


async def test_api_client_network_error_returns_message():
    from unittest.mock import AsyncMock, patch
    import httpx
    from nori.tools.api_client import ApiClient

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await ApiClient(url="http://example.com", reason="r")
    assert "[network error]" in result.result


async def test_api_client_returns_response_body():
    from unittest.mock import AsyncMock, MagicMock, patch
    from nori.tools.api_client import ApiClient

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "Hello from server"

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await ApiClient(url="http://example.com", reason="r")
    assert "Hello from server" in result.result


async def test_api_client_http_error_returns_status():
    from unittest.mock import AsyncMock, MagicMock, patch
    from nori.tools.api_client import ApiClient

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = "Not Found"

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await ApiClient(url="http://example.com/missing", reason="r")
    assert "404" in result.result


async def test_api_client_method_passed_through():
    from unittest.mock import AsyncMock, MagicMock, patch
    from nori.tools.api_client import ApiClient

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "ok"

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await ApiClient(url="http://example.com", method="POST", body="data", reason="r")
    call_kwargs = mock_client.request.call_args
    assert call_kwargs.args[0] == "POST"


# ── CodeRunner ────────────────────────────────────────────────────────────────

async def test_code_runner_stdout_returned():
    from nori.tools.code_runner import CodeRunner
    result = await CodeRunner(code="print('hello nori')", reason="r")
    assert "hello nori" in result.result


async def test_code_runner_exception_returned_not_raised():
    from nori.tools.code_runner import CodeRunner
    result = await CodeRunner(code="raise ValueError('boom')", reason="r")
    assert "[error]" in result.result
    assert "boom" in result.result


async def test_code_runner_reason_not_in_snippet():
    from unittest.mock import MagicMock, patch
    from nori.tools.code_runner import CodeRunner
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        await CodeRunner(code="print(1)", reason="secret reason")
        args = mock_run.call_args.args[0]
        assert "secret reason" not in " ".join(args)


# ── FileRead ──────────────────────────────────────────────────────────────────

async def test_file_read_returns_contents(tmp_path):
    from nori.tools.file_read import FileRead
    f = tmp_path / "hello.txt"
    f.write_text("line one\nline two\n")
    result = await FileRead(path=str(f), reason="r")
    assert "line one" in result.result
    assert "line two" in result.result


async def test_file_read_range_returns_numbered_lines(tmp_path):
    from nori.tools.file_read import FileRead
    f = tmp_path / "code.py"
    f.write_text("a\nb\nc\nd\ne\n")
    result = await FileRead(path=str(f), start_line=2, end_line=4, reason="r")
    assert "2" in result.result
    assert "b" in result.result
    assert "d" in result.result
    assert "a" not in result.result
    assert "e" not in result.result


async def test_file_read_missing_file(tmp_path):
    from nori.tools.file_read import FileRead
    result = await FileRead(path=str(tmp_path / "missing.txt"), reason="r")
    assert "not found" in result.result.lower()


async def test_file_read_truncates_large_file(tmp_path):
    from nori.tools.file_read import FileRead
    f = tmp_path / "big.txt"
    f.write_text("x" * 60_000)
    result = await FileRead(path=str(f), reason="r")
    assert "truncated" in result.result
    assert len(result.result) < 55_000


async def test_file_read_reason_not_in_output(tmp_path):
    from nori.tools.file_read import FileRead
    f = tmp_path / "file.txt"
    f.write_text("content")
    result = await FileRead(path=str(f), reason="secret reason")
    assert "secret reason" not in result.result


# ── FileWrite ─────────────────────────────────────────────────────────────────

async def test_file_write_creates_file(tmp_path):
    from nori.tools.file_write import FileWrite
    dest = tmp_path / "new.txt"
    await FileWrite(path=str(dest), content="hello nori", reason="r")
    assert dest.read_text() == "hello nori"


async def test_file_write_overwrites_existing(tmp_path):
    from nori.tools.file_write import FileWrite
    dest = tmp_path / "existing.txt"
    dest.write_text("old content")
    await FileWrite(path=str(dest), content="new content", reason="r")
    assert dest.read_text() == "new content"


async def test_file_write_creates_parent_dirs(tmp_path):
    from nori.tools.file_write import FileWrite
    dest = tmp_path / "a" / "b" / "c" / "file.txt"
    await FileWrite(path=str(dest), content="deep", reason="r")
    assert dest.read_text() == "deep"


async def test_file_write_returns_byte_count(tmp_path):
    from nori.tools.file_write import FileWrite
    dest = tmp_path / "out.txt"
    result = await FileWrite(path=str(dest), content="hello", reason="r")
    assert "5" in result.result
    assert str(dest) in result.result


async def test_file_write_reason_not_written(tmp_path):
    from nori.tools.file_write import FileWrite
    dest = tmp_path / "out.txt"
    await FileWrite(path=str(dest), content="data", reason="secret reason")
    assert "secret reason" not in dest.read_text()
