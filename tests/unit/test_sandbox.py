"""Tests for _sandbox.py sandbox enforcement — check_command and check_path."""

import pytest
from nori.tools._sandbox import check_command, check_path, sandbox_dir


# ── check_command ─────────────────────────────────────────────────────────────

def test_check_command_clean_returns_none():
    assert check_command("ls -la", "/allowed") is None


def test_check_command_relative_path_returns_none():
    # Relative paths don't match the absolute-path regex
    assert check_command("cat ./file.txt", "/allowed") is None


def test_check_command_violation_returns_error():
    error = check_command("cat /etc/passwd", "/allowed")
    assert error is not None
    assert "Sandbox violation" in error
    assert "/etc/passwd" in error
    assert "/allowed" in error


def test_check_command_path_inside_allowed_returns_none():
    assert check_command("cat /allowed/subdir/file.txt", "/allowed") is None


def test_check_command_multiple_paths_stops_at_first_violation():
    error = check_command("cat /etc/passwd /allowed/ok.txt", "/allowed")
    assert error is not None
    assert "/etc/passwd" in error


# ── check_path ────────────────────────────────────────────────────────────────

def test_check_path_clean_returns_none():
    assert check_path("/allowed/file.txt", "/allowed") is None


def test_check_path_violation_returns_error():
    error = check_path("/etc/passwd", "/allowed")
    assert error is not None
    assert "Sandbox violation" in error
    assert "/etc/passwd" in error
    assert "/allowed" in error


def test_check_path_relative_resolves_inside_allowed(tmp_path):
    allowed = str(tmp_path)
    assert check_path("subdir/file.txt", allowed) is None


def test_check_path_relative_traversal_is_caught(tmp_path):
    allowed = str(tmp_path)
    error = check_path("../../etc/passwd", allowed)
    assert error is not None
    assert "Sandbox violation" in error


def test_check_path_sibling_prefix_is_caught(tmp_path):
    """A sibling dir sharing a name prefix must not count as inside the sandbox."""
    allowed = tmp_path / "box"
    allowed.mkdir()
    sibling = tmp_path / "box_evil"
    sibling.mkdir()
    error = check_path(str(sibling / "secret.txt"), str(allowed))
    assert error is not None
    assert "Sandbox violation" in error


def test_check_path_symlink_escape_is_caught(tmp_path):
    """A symlink inside the sandbox pointing outside must not be followed out."""
    allowed = tmp_path / "box"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("top secret")
    (allowed / "link").symlink_to(outside)
    error = check_path("link/secret.txt", str(allowed))
    assert error is not None
    assert "Sandbox violation" in error


def test_check_command_sibling_prefix_is_caught():
    error = check_command("cat /allowed_evil/secret.txt", "/allowed")
    assert error is not None
    assert "Sandbox violation" in error


def test_check_command_relative_traversal_is_caught():
    error = check_command("cat ../../etc/passwd", "/allowed")
    assert error is not None
    assert "Sandbox violation" in error


# ── sandbox_dir context var enforced through tools ────────────────────────────

async def test_bash_sandbox_blocks_violation(tmp_path):
    from nori.tools.bash import Bash
    token = sandbox_dir.set(str(tmp_path))
    try:
        result = await Bash(command="cat /etc/passwd", reason="r")
        assert "[error]" in result.result
        assert "Sandbox violation" in result.result
    finally:
        sandbox_dir.reset(token)


async def test_bash_sandbox_allows_relative_command(tmp_path):
    from nori.tools.bash import Bash
    (tmp_path / "hello.txt").write_text("hi")
    token = sandbox_dir.set(str(tmp_path))
    try:
        result = await Bash(command="cat hello.txt", reason="r")
        assert "hi" in result.result
    finally:
        sandbox_dir.reset(token)


async def test_file_read_sandbox_blocks_violation(tmp_path):
    from nori.tools.file_read import FileRead
    token = sandbox_dir.set(str(tmp_path))
    try:
        result = await FileRead(path="/etc/passwd", reason="r")
        assert "[error]" in result.result
        assert "Sandbox violation" in result.result
    finally:
        sandbox_dir.reset(token)


async def test_file_write_sandbox_blocks_violation(tmp_path):
    from nori.tools.file_write import FileWrite
    token = sandbox_dir.set(str(tmp_path))
    try:
        result = await FileWrite(path="/etc/evil.txt", content="x", reason="r")
        assert "[error]" in result.result
        assert "Sandbox violation" in result.result
    finally:
        sandbox_dir.reset(token)


async def test_file_edit_sandbox_blocks_violation(tmp_path):
    from nori.tools.file_edit import FileEdit
    token = sandbox_dir.set(str(tmp_path))
    try:
        result = await FileEdit(path="/etc/passwd", old_content="x", new_content="y", reason="r")
        assert "[error]" in result.result
    finally:
        sandbox_dir.reset(token)


async def test_file_search_sandbox_blocks_violation(tmp_path):
    from nori.tools.file_search import FileSearch
    token = sandbox_dir.set(str(tmp_path))
    try:
        result = await FileSearch(path="/etc", pattern="*", reason="r")
        assert "[error]" in result.result
    finally:
        sandbox_dir.reset(token)


async def test_code_runner_sandbox_blocks_violation(tmp_path):
    from nori.tools.code_runner import CodeRunner
    token = sandbox_dir.set(str(tmp_path))
    try:
        result = await CodeRunner(code="import os; os.remove('/etc/passwd')", reason="r")
        assert "[error]" in result.result
        assert "Sandbox violation" in result.result
    finally:
        sandbox_dir.reset(token)


async def test_code_runner_sandbox_allows_clean_code(tmp_path):
    from nori.tools.code_runner import CodeRunner
    token = sandbox_dir.set(str(tmp_path))
    try:
        result = await CodeRunner(code="print('safe')", reason="r")
        assert "safe" in result.result
    finally:
        sandbox_dir.reset(token)
