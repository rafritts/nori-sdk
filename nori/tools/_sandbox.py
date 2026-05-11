import os
import re
from contextvars import ContextVar
from pathlib import Path

# When set, file and shell tools are restricted to this directory.
sandbox_dir: ContextVar[str | None] = ContextVar("nori_sandbox_dir", default=None)

_ABS_PATH_RE = re.compile(r'(?<![.\w])(\/[^\s\'\";|&><(){}$`\\]+)')


def check_command(command: str, allowed: str) -> str | None:
    """Return an error string if command references an absolute path outside allowed, else None."""
    for match in _ABS_PATH_RE.finditer(command):
        path = os.path.normpath(match.group(1))
        if not path.startswith(allowed):
            return (
                f"Sandbox violation: '{match.group(1)}' is outside the allowed directory '{allowed}'. "
                f"Use relative paths or paths within the project directory."
            )
    return None


def check_path(path: str, allowed: str) -> str | None:
    """Return an error string if path resolves outside allowed, else None."""
    resolved = os.path.normpath(os.path.join(allowed, path) if not os.path.isabs(path) else path)
    if not resolved.startswith(allowed):
        return (
            f"Sandbox violation: '{path}' is outside the allowed directory '{allowed}'. "
            f"Use relative paths or paths within the project directory."
        )
    return None
