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
