import os
import re
from contextvars import ContextVar
from pathlib import Path

# When set, file and shell tools are restricted to this directory.
#
# IMPORTANT: this is a *guardrail*, not a security boundary. check_path resolves
# symlinks and enforces a real directory boundary, so it reliably confines the
# file tools. check_command only pattern-scans shell/Python source and is
# trivially bypassable (env expansion, command substitution, dynamically built
# paths); treat Bash/CodeRunner as having the full privileges of the host
# process. For real isolation, run the process in a container / unprivileged
# user / network namespace. See docs/security.md.
sandbox_dir: ContextVar[str | None] = ContextVar("nori_sandbox_dir", default=None)

_ABS_PATH_RE = re.compile(r'(?<![.\w])(\/[^\s\'\";|&><(){}$`\\]+)')
_TRAVERSAL_RE = re.compile(r'(?:^|[\s=:,"\'(\[])(\.\.\/)')


def _is_within(resolved: str, allowed: str) -> bool:
    """True if resolved is allowed itself or a path beneath it (boundary-aware)."""
    return resolved == allowed or resolved.startswith(allowed + os.sep)


def check_command(command: str, allowed: str) -> str | None:
    """Best-effort guardrail against a command reaching outside `allowed`.

    NOT a security boundary — it only pattern-matches literal paths and cannot
    see through shell expansion, command substitution, or dynamically built
    paths. See docs/security.md. Returns an error string on an obvious
    violation, else None.
    """
    allowed = os.path.realpath(allowed)
    for match in _ABS_PATH_RE.finditer(command):
        path = os.path.normpath(match.group(1))
        if not _is_within(path, allowed):
            return (
                f"Sandbox violation: '{match.group(1)}' is outside the allowed directory '{allowed}'. "
                f"Use relative paths or paths within the project directory."
            )
    if _TRAVERSAL_RE.search(command):
        return (
            "Sandbox violation: relative path traversal ('..') is not allowed. "
            "Use paths within the project directory."
        )
    return None


def check_path(path: str, allowed: str) -> str | None:
    """Return an error string if path resolves outside allowed, else None.

    Resolves symlinks (realpath) so a symlink inside the sandbox cannot point
    out of it, and compares on a directory boundary so a sibling directory like
    '/allowed_evil' is not mistaken for being inside '/allowed'.
    """
    allowed_real = os.path.realpath(allowed)
    target = path if os.path.isabs(path) else os.path.join(allowed_real, path)
    resolved = os.path.realpath(target)
    if not _is_within(resolved, allowed_real):
        return (
            f"Sandbox violation: '{path}' is outside the allowed directory '{allowed}'. "
            f"Use relative paths or paths within the project directory."
        )
    return None
