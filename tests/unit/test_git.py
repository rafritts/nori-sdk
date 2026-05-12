import subprocess
import pytest


@pytest.fixture
def repo(tmp_path):
    """Minimal git repo with one commit."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@nori.dev"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Nori Test"], cwd=tmp_path, check=True, capture_output=True)
    f = tmp_path / "hello.txt"
    f.write_text("hello")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


# ── status ────────────────────────────────────────────────────────────────────

async def test_git_status_clean_repo(repo):
    from nori.tools.git import Git
    result = await Git(operation="status", repo_path=str(repo), reason="r")
    assert "error" not in result.result.lower()


async def test_git_status_shows_modified_file(repo):
    from nori.tools.git import Git
    (repo / "hello.txt").write_text("changed")
    result = await Git(operation="status", repo_path=str(repo), reason="r")
    assert "hello.txt" in result.result


# ── diff ──────────────────────────────────────────────────────────────────────

async def test_git_diff_unstaged(repo):
    from nori.tools.git import Git
    (repo / "hello.txt").write_text("changed content")
    result = await Git(operation="diff", repo_path=str(repo), reason="r")
    assert "hello" in result.result or "changed" in result.result


async def test_git_diff_no_changes_returns_message(repo):
    from nori.tools.git import Git
    result = await Git(operation="diff", repo_path=str(repo), reason="r")
    assert "No differences" in result.result


async def test_git_diff_staged(repo):
    from nori.tools.git import Git
    (repo / "hello.txt").write_text("staged change")
    subprocess.run(["git", "add", "hello.txt"], cwd=repo, check=True, capture_output=True)
    result = await Git(operation="diff", staged=True, repo_path=str(repo), reason="r")
    assert "staged" in result.result or "hello" in result.result


# ── log ───────────────────────────────────────────────────────────────────────

async def test_git_log_shows_commit(repo):
    from nori.tools.git import Git
    result = await Git(operation="log", repo_path=str(repo), reason="r")
    assert "init" in result.result


async def test_git_log_respects_n(repo):
    from nori.tools.git import Git
    # add a second commit
    (repo / "b.txt").write_text("b")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "second"], cwd=repo, check=True, capture_output=True)
    result = await Git(operation="log", n=1, repo_path=str(repo), reason="r")
    assert len(result.result.splitlines()) == 1


# ── add / add_all / commit ────────────────────────────────────────────────────

async def test_git_add_stages_file(repo):
    from nori.tools.git import Git
    (repo / "new.txt").write_text("new")
    result = await Git(operation="add", paths=["new.txt"], repo_path=str(repo), reason="r")
    assert "new.txt" in result.result


async def test_git_add_without_paths_returns_error(repo):
    from nori.tools.git import Git
    result = await Git(operation="add", repo_path=str(repo), reason="r")
    assert "[error]" in result.result


async def test_git_add_all_and_commit(repo):
    from nori.tools.git import Git
    (repo / "c.txt").write_text("c")
    await Git(operation="add_all", repo_path=str(repo), reason="r")
    result = await Git(operation="commit", message="add c", repo_path=str(repo), reason="r")
    assert "[git error]" not in result.result


async def test_git_commit_without_message_returns_error(repo):
    from nori.tools.git import Git
    result = await Git(operation="commit", repo_path=str(repo), reason="r")
    assert "[error]" in result.result


# ── branch ────────────────────────────────────────────────────────────────────

async def test_git_branch_list(repo):
    from nori.tools.git import Git
    result = await Git(operation="branch", action="list", repo_path=str(repo), reason="r")
    assert "error" not in result.result.lower()


async def test_git_branch_create(repo):
    from nori.tools.git import Git
    result = await Git(operation="branch", action="create", name="feature/test", repo_path=str(repo), reason="r")
    assert "[git error]" not in result.result


async def test_git_branch_delete_without_allow_destructive(repo):
    from nori.tools.git import Git
    result = await Git(operation="branch", action="delete", name="main", repo_path=str(repo), reason="r")
    assert "[error]" in result.result
    assert "allow_destructive" in result.result


async def test_git_branch_delete_with_allow_destructive(repo):
    from nori.tools.git import Git
    # create a branch to delete
    subprocess.run(["git", "branch", "to-delete"], cwd=repo, check=True, capture_output=True)
    result = await Git(operation="branch", action="delete", name="to-delete",
                       allow_destructive=True, repo_path=str(repo), reason="r")
    assert "[error]" not in result.result


# ── reset ─────────────────────────────────────────────────────────────────────

async def test_git_reset_soft_allowed_by_default(repo):
    from nori.tools.git import Git
    # need a second commit to reset
    (repo / "x.txt").write_text("x")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "second"], cwd=repo, check=True, capture_output=True)
    result = await Git(operation="reset", mode="soft", ref="HEAD~1", repo_path=str(repo), reason="r")
    assert "[error]" not in result.result


async def test_git_reset_hard_blocked_without_flag(repo):
    from nori.tools.git import Git
    result = await Git(operation="reset", mode="hard", repo_path=str(repo), reason="r")
    assert "[error]" in result.result
    assert "allow_destructive" in result.result


async def test_git_reset_mixed_blocked_without_flag(repo):
    from nori.tools.git import Git
    result = await Git(operation="reset", mode="mixed", repo_path=str(repo), reason="r")
    assert "[error]" in result.result


# ── checkout ──────────────────────────────────────────────────────────────────

async def test_git_checkout_requires_target(repo):
    from nori.tools.git import Git
    result = await Git(operation="checkout", repo_path=str(repo), reason="r")
    assert "[error]" in result.result


# ── stash ─────────────────────────────────────────────────────────────────────

async def test_git_stash_list_empty(repo):
    from nori.tools.git import Git
    result = await Git(operation="stash", action="list", repo_path=str(repo), reason="r")
    assert "no stashes" in result.result.lower() or result.result


async def test_git_stash_push_and_pop(repo):
    from nori.tools.git import Git
    (repo / "hello.txt").write_text("stashed change")
    push_result = await Git(operation="stash", action="push", message="wip", repo_path=str(repo), reason="r")
    assert "[git error]" not in push_result.result
    pop_result = await Git(operation="stash", action="pop", repo_path=str(repo), reason="r")
    assert "[git error]" not in pop_result.result


# ── unknown operation ─────────────────────────────────────────────────────────

async def test_git_unknown_operation_returns_error(repo):
    from nori.tools.git import Git
    result = await Git(operation="teleport", repo_path=str(repo), reason="r")
    assert "[error]" in result.result
    assert "teleport" in result.result


# ── schema ────────────────────────────────────────────────────────────────────

def test_git_schema_has_reason_required():
    from nori.tools.git import Git
    assert "reason" in Git.schema["function"]["parameters"]["required"]


def test_git_schema_operation_required():
    from nori.tools.git import Git
    assert "operation" in Git.schema["function"]["parameters"]["required"]


# ── diff with paths / truncation ──────────────────────────────────────────────

async def test_git_diff_with_paths(repo):
    from nori.tools.git import Git
    (repo / "hello.txt").write_text("changed content")
    result = await Git(operation="diff", paths=["hello.txt"], repo_path=str(repo), reason="r")
    assert "hello" in result.result or "changed" in result.result or "No differences" in result.result


async def test_git_diff_truncates_large_diff(repo):
    from unittest.mock import patch
    from nori.tools.git import Git
    big_output = "+" + "x" * 25_000
    with patch("nori.tools.git._run", return_value=(big_output, "", 0)):
        result = await Git(operation="diff", repo_path=str(repo), reason="r")
    assert "truncated" in result.result


async def test_git_diff_git_error(repo):
    from unittest.mock import patch
    from nori.tools.git import Git
    with patch("nori.tools.git._run", return_value=("", "fatal: bad rev", 128)):
        result = await Git(operation="diff", repo_path=str(repo), reason="r")
    assert "[git error]" in result.result


# ── log with branch ───────────────────────────────────────────────────────────

async def test_git_log_with_branch(repo):
    from nori.tools.git import Git
    result = await Git(operation="log", branch="HEAD", repo_path=str(repo), reason="r")
    assert "init" in result.result or "error" not in result.result.lower()


# ── push / pull with branch ───────────────────────────────────────────────────

async def test_git_push_with_branch(repo):
    from unittest.mock import patch
    from nori.tools.git import Git
    with patch("nori.tools.git._run", return_value=("Everything up-to-date", "", 0)):
        result = await Git(operation="push", branch="main", remote="origin", repo_path=str(repo), reason="r")
    assert "up-to-date" in result.result or "error" not in result.result.lower()


async def test_git_pull_with_branch(repo):
    from unittest.mock import patch
    from nori.tools.git import Git
    with patch("nori.tools.git._run", return_value=("Already up to date.", "", 0)):
        result = await Git(operation="pull", branch="main", remote="origin", repo_path=str(repo), reason="r")
    assert "up to date" in result.result or "error" not in result.result.lower()


async def test_git_push_no_branch(repo):
    from unittest.mock import patch
    from nori.tools.git import Git
    with patch("nori.tools.git._run", return_value=("Everything up-to-date", "", 0)):
        result = await Git(operation="push", repo_path=str(repo), reason="r")
    assert "error" not in result.result.lower() or "up-to-date" in result.result


async def test_git_pull_no_branch(repo):
    from unittest.mock import patch
    from nori.tools.git import Git
    with patch("nori.tools.git._run", return_value=("Already up to date.", "", 0)):
        result = await Git(operation="pull", repo_path=str(repo), reason="r")
    assert "error" not in result.result.lower() or "up to date" in result.result


# ── branch edge cases ─────────────────────────────────────────────────────────

async def test_git_branch_create_without_name(repo):
    from nori.tools.git import Git
    result = await Git(operation="branch", action="create", repo_path=str(repo), reason="r")
    assert "[error]" in result.result
    assert "name" in result.result


async def test_git_branch_delete_without_name(repo):
    from nori.tools.git import Git
    result = await Git(operation="branch", action="delete", allow_destructive=True,
                       repo_path=str(repo), reason="r")
    assert "[error]" in result.result
    assert "name" in result.result


async def test_git_branch_unknown_action(repo):
    from nori.tools.git import Git
    result = await Git(operation="branch", action="teleport", repo_path=str(repo), reason="r")
    assert "[error]" in result.result
    assert "teleport" in result.result


# ── checkout success ──────────────────────────────────────────────────────────

async def test_git_checkout_success(repo):
    from nori.tools.git import Git
    # Create a branch first, then check it out
    subprocess.run(["git", "branch", "my-branch"], cwd=repo, check=True, capture_output=True)
    result = await Git(operation="checkout", target="my-branch", repo_path=str(repo), reason="r")
    assert "[git error]" not in result.result


# ── reset unknown mode ────────────────────────────────────────────────────────

async def test_git_reset_unknown_mode(repo):
    from nori.tools.git import Git
    result = await Git(operation="reset", mode="turbo", allow_destructive=True,
                       repo_path=str(repo), reason="r")
    assert "[error]" in result.result
    assert "turbo" in result.result


async def test_git_reset_hard_with_flag(repo):
    from nori.tools.git import Git
    # need second commit to reset to
    (repo / "x.txt").write_text("x")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "second"], cwd=repo, check=True, capture_output=True)
    result = await Git(operation="reset", mode="hard", allow_destructive=True,
                       ref="HEAD~1", repo_path=str(repo), reason="r")
    assert "[error]" not in result.result


# ── stash unknown action ──────────────────────────────────────────────────────

async def test_git_stash_unknown_action(repo):
    from nori.tools.git import Git
    result = await Git(operation="stash", action="teleport", repo_path=str(repo), reason="r")
    assert "[error]" in result.result
    assert "teleport" in result.result


async def test_git_add_git_error(repo):
    from unittest.mock import patch
    from nori.tools.git import Git
    with patch("nori.tools.git._run", return_value=("", "fatal: pathspec 'x' did not match", 128)):
        result = await Git(operation="add", paths=["x"], repo_path=str(repo), reason="r")
    assert "[git error]" in result.result


async def test_git_add_all_git_error(repo):
    from unittest.mock import patch
    from nori.tools.git import Git
    with patch("nori.tools.git._run", return_value=("", "fatal: not a git repo", 128)):
        result = await Git(operation="add_all", repo_path=str(repo), reason="r")
    assert "[git error]" in result.result


# ── sandbox violation for repo_path ──────────────────────────────────────────

async def test_git_repo_path_sandbox_violation(tmp_path):
    from nori.tools.git import Git
    from nori.tools._sandbox import sandbox_dir
    allowed = str(tmp_path / "allowed")
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    evil_path = str(tmp_path / "evil")
    token = sandbox_dir.set(allowed)
    try:
        result = await Git(operation="status", repo_path=evil_path, reason="r")
        assert "[error]" in result.result
        assert "Sandbox violation" in result.result
    finally:
        sandbox_dir.reset(token)
