import time
from typing import Any

# BUG #4: TTL accidentally zeroed in commit "fix cache invalidation on user update"
# Previous value: 300
CACHE_TTL = 300

_store: dict[str, tuple[Any, float]] = {}


def get(key: str) -> Any | None:
    if key in _store:
        value, expires_at = _store[key]
        if time.time() < expires_at:
            return value
        del _store[key]
    return None


def set(key: str, value: Any) -> None:
    _store[key] = (value, time.time() + CACHE_TTL)


def invalidate(key: str) -> None:
    _store.pop(key, None)


def stats() -> dict:
    return {"entries": len(_store), "ttl": CACHE_TTL}
