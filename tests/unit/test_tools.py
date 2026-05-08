import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Bash ──────────────────────────────────────────────────────────────────────

async def test_bash_stdout_returned():
    from nori.tools.bash import Bash
    result = await Bash(command="echo hello", reason="test")
    assert "hello" in result


async def test_bash_stderr_returned():
    from nori.tools.bash import Bash
    result = await Bash(command="echo err >&2", reason="test")
    assert "err" in result


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
    assert "foo.py" in result
    assert "bar.txt" not in result


async def test_file_search_finds_by_content(tmp_path):
    from nori.tools.file_search import FileSearch
    (tmp_path / "a.txt").write_text("hello nori world")
    (tmp_path / "b.txt").write_text("unrelated")
    result = await FileSearch(path=str(tmp_path), pattern="*", content="nori", reason="r")
    assert "a.txt" in result
    assert "b.txt" not in result


async def test_file_search_no_match_returns_empty(tmp_path):
    from nori.tools.file_search import FileSearch
    result = await FileSearch(path=str(tmp_path), pattern="*.xyz", reason="r")
    assert result == "No matches found."


# ── WebClient ─────────────────────────────────────────────────────────────────

async def test_web_client_returns_response_body():
    from unittest.mock import AsyncMock, MagicMock, patch
    from nori.tools.web_client import WebClient

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "Hello from server"

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await WebClient(url="http://example.com", reason="r")
    assert "Hello from server" in result


async def test_web_client_http_error_returns_status():
    from unittest.mock import AsyncMock, MagicMock, patch
    from nori.tools.web_client import WebClient

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = "Not Found"

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await WebClient(url="http://example.com/missing", reason="r")
    assert "404" in result


async def test_web_client_method_passed_through():
    from unittest.mock import AsyncMock, MagicMock, patch
    from nori.tools.web_client import WebClient

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "ok"

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await WebClient(url="http://example.com", method="POST", body="data", reason="r")
    call_kwargs = mock_client.request.call_args
    assert call_kwargs.args[0] == "POST"
