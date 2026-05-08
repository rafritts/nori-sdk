import fnmatch

from nori.exceptions import PermissionError


class PermissionGuard:
    def __init__(self, allow: list[str] | None, deny: list[str] | None):
        if allow and deny:
            raise RuntimeError("Declare either 'allow' or 'deny', not both.")
        self._allow = allow or []
        self._deny = deny or []

    def check(self, tool_name: str) -> None:
        if self._deny:
            if any(fnmatch.fnmatch(tool_name, pat) for pat in self._deny):
                raise PermissionError(f"Tool '{tool_name}' is denied.")
        elif self._allow:
            if not any(fnmatch.fnmatch(tool_name, pat) for pat in self._allow):
                raise PermissionError(f"Tool '{tool_name}' is not in the allow list.")
