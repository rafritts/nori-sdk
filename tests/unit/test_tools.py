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
