import subprocess
from pathlib import Path

from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools._sandbox import sandbox_dir, check_path

_DIFF_CAP = 20_000


def _run(args: list[str], cwd: str) -> tuple[str, str, int]:
    proc = subprocess.run(args, capture_output=True, text=True, cwd=cwd)
    return proc.stdout.strip(), proc.stderr.strip(), proc.returncode


def _ok(stdout: str, stderr: str, rc: int) -> ToolResult:
    out = stdout or stderr or "(no output)"
    if rc != 0:
        return ToolResult(result=f"[git error]\n{stderr or stdout}")
    return ToolResult(result=out)


@tool
def Git(
    operation: str,
    allow_destructive: bool = False,
    # diff / add
    staged: bool = False,
    paths: list = None,
    # log
    n: int = 20,
    # commit / stash
    message: str = "",
    # push / pull
    remote: str = "origin",
    branch: str = "",
    # branch / stash
    action: str = "",
    name: str = "",
    # reset
    mode: str = "soft",
    ref: str = "HEAD~1",
    # checkout
    target: str = "",
    # working directory override
    repo_path: str = "",
) -> ToolResult:
    """Run a git operation in the working directory. Supported operations:
    status, diff, log, add, add_all, commit, push, pull, branch, checkout,
    reset, stash. Destructive operations (reset hard/mixed, branch delete)
    require allow_destructive=True at bind time."""

    allowed_sandbox = sandbox_dir.get()
    cwd = str(Path.cwd())

    if repo_path:
        if allowed_sandbox:
            error = check_path(repo_path, allowed_sandbox)
            if error:
                return ToolResult(result=f"[error]\n{error}")
        cwd = repo_path

    op = operation.lower()

    if op == "status":
        stdout, stderr, rc = _run(["git", "status", "--short", "-b"], cwd)
        return _ok(stdout, stderr, rc)

    elif op == "diff":
        cmd = ["git", "diff"]
        if staged:
            cmd.append("--staged")
        if paths:
            cmd += ["--"] + paths
        stdout, stderr, rc = _run(cmd, cwd)
        if rc != 0:
            return ToolResult(result=f"[git error]\n{stderr}")
        if not stdout:
            return ToolResult(result="No differences.")
        if len(stdout) > _DIFF_CAP:
            omitted = len(stdout) - _DIFF_CAP
            stdout = stdout[:_DIFF_CAP] + f"\n[truncated — {omitted:,} chars omitted]"
        return ToolResult(result=stdout)

    elif op == "log":
        cmd = ["git", "log", f"-{n}", "--oneline", "--format=%h %as %an %s"]
        if branch:
            cmd.append(branch)
        stdout, stderr, rc = _run(cmd, cwd)
        return _ok(stdout, stderr, rc)

    elif op == "add":
        if not paths:
            return ToolResult(result="[error] add requires paths list")
        stdout, stderr, rc = _run(["git", "add", "--"] + paths, cwd)
        if rc != 0:
            return ToolResult(result=f"[git error]\n{stderr}")
        return ToolResult(result=f"Staged: {', '.join(paths)}")

    elif op == "add_all":
        stdout, stderr, rc = _run(["git", "add", "-A"], cwd)
        if rc != 0:
            return ToolResult(result=f"[git error]\n{stderr}")
        return ToolResult(result="Staged all changes.")

    elif op == "commit":
        if not message:
            return ToolResult(result="[error] commit requires message")
        stdout, stderr, rc = _run(["git", "commit", "-m", message], cwd)
        return _ok(stdout, stderr, rc)

    elif op == "push":
        cmd = ["git", "push", remote]
        if branch:
            cmd.append(branch)
        stdout, stderr, rc = _run(cmd, cwd)
        return _ok(stdout or stderr, "", rc)

    elif op == "pull":
        cmd = ["git", "pull", remote]
        if branch:
            cmd.append(branch)
        stdout, stderr, rc = _run(cmd, cwd)
        return _ok(stdout or stderr, "", rc)

    elif op == "branch":
        act = action.lower() if action else "list"
        if act == "list":
            stdout, stderr, rc = _run(["git", "branch", "-a"], cwd)
            return _ok(stdout, stderr, rc)
        elif act == "create":
            if not name:
                return ToolResult(result="[error] branch create requires name")
            stdout, stderr, rc = _run(["git", "checkout", "-b", name], cwd)
            return _ok(stdout or stderr, "", rc)
        elif act == "delete":
            if not allow_destructive:
                return ToolResult(result="[error] branch delete is destructive — bind Git with allow_destructive=True to enable it")
            if not name:
                return ToolResult(result="[error] branch delete requires name")
            stdout, stderr, rc = _run(["git", "branch", "-d", name], cwd)
            return _ok(stdout or stderr, stderr, rc)
        else:
            return ToolResult(result=f"[error] unknown branch action: {action!r}. Use list, create, or delete.")

    elif op == "checkout":
        if not target:
            return ToolResult(result="[error] checkout requires target")
        stdout, stderr, rc = _run(["git", "checkout", target], cwd)
        return _ok(stdout or stderr, "", rc)

    elif op == "reset":
        m = mode.lower()
        if m in ("hard", "mixed") and not allow_destructive:
            return ToolResult(result=f"[error] reset --{m} is destructive — bind Git with allow_destructive=True to enable it")
        if m not in ("soft", "mixed", "hard"):
            return ToolResult(result=f"[error] unknown reset mode: {mode!r}. Use soft, mixed, or hard.")
        stdout, stderr, rc = _run(["git", "reset", f"--{m}", ref], cwd)
        return _ok(stdout or stderr, stderr, rc)

    elif op == "stash":
        act = action.lower() if action else "push"
        if act == "push":
            cmd = ["git", "stash", "push"]
            if message:
                cmd += ["-m", message]
            stdout, stderr, rc = _run(cmd, cwd)
            return _ok(stdout or stderr, stderr, rc)
        elif act == "pop":
            stdout, stderr, rc = _run(["git", "stash", "pop"], cwd)
            return _ok(stdout or stderr, stderr, rc)
        elif act == "list":
            stdout, stderr, rc = _run(["git", "stash", "list"], cwd)
            return _ok(stdout or "(no stashes)", stderr, rc)
        else:
            return ToolResult(result=f"[error] unknown stash action: {action!r}. Use push, pop, or list.")

    else:
        return ToolResult(result=f"[error] unknown operation: {operation!r}")
