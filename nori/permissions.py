import fnmatch
from dataclasses import dataclass, field

from nori.exceptions import ToolPermissionError


@dataclass
class Permissions:
    allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.allow and self.deny:
            raise ValueError("Declare either allow or deny, not both.")


class PermissionGuard:
    def __init__(self, allow: list[str] | None, deny: list[str] | None):
        if allow and deny:
            raise RuntimeError("Declare either 'allow' or 'deny', not both.")
        self._allow = allow or []
        self._deny = deny or []

    def check(self, tool_name: str) -> None:
        if self._deny:
            if any(fnmatch.fnmatch(tool_name, pat) for pat in self._deny):
                raise ToolPermissionError(f"Tool '{tool_name}' is denied.")
        elif self._allow:
            if not any(fnmatch.fnmatch(tool_name, pat) for pat in self._allow):
                raise ToolPermissionError(f"Tool '{tool_name}' is not in the allow list.")
