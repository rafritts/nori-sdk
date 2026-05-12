import os

import redis.asyncio as aioredis

from nori.tool import tool
from nori.tools.base import ToolResult

_clients: dict[str, aioredis.Redis] = {}


def _client(dsn: str = "") -> aioredis.Redis:
    dsn = dsn or os.environ["REDIS_DSN"]
    if dsn not in _clients:
        _clients[dsn] = aioredis.from_url(dsn, decode_responses=True)
    return _clients[dsn]


@tool
async def Redis(
    operation: str,
    key: str = "",
    value: str = "",
    pattern: str = "*",
    ttl: int = 0,
    keys: list = None,
    dsn: str = "",
) -> ToolResult:
    """Interact with a Redis instance. Operations:
    - get: retrieve the value for a key
    - set: store a value (pass ttl in seconds to set expiry)
    - delete: remove one or more keys (pass key or keys list)
    - keys: list keys matching a pattern (default: *)
    - ttl: get the remaining time-to-live for a key in seconds
    - expire: set or update the TTL for a key
    """
    try:
        client = _client(dsn)
    except KeyError:
        return ToolResult(result="[error] REDIS_DSN not set")

    op = operation.lower()

    try:
        if op == "get":
            if not key:
                return ToolResult(result="[error] get requires a key")
            val = await client.get(key)
            return ToolResult(result=val if val is not None else "(key not found)")

        elif op == "set":
            if not key:
                return ToolResult(result="[error] set requires a key")
            if ttl > 0:
                await client.setex(key, ttl, value)
            else:
                await client.set(key, value)
            return ToolResult(result=f"OK — set {key!r}")

        elif op == "delete":
            targets = keys or ([key] if key else [])
            if not targets:
                return ToolResult(result="[error] delete requires key or keys")
            count = await client.delete(*targets)
            return ToolResult(result=f"Deleted {count} key(s)")

        elif op == "keys":
            matches = await client.keys(pattern)
            if not matches:
                return ToolResult(result="(no keys matched)")
            return ToolResult(result="\n".join(sorted(matches)))

        elif op == "ttl":
            if not key:
                return ToolResult(result="[error] ttl requires a key")
            val = await client.ttl(key)
            if val == -2:
                return ToolResult(result="(key does not exist)")
            if val == -1:
                return ToolResult(result="(no expiry set)")
            return ToolResult(result=f"{val}s remaining")

        elif op == "expire":
            if not key or ttl <= 0:
                return ToolResult(result="[error] expire requires key and ttl > 0")
            await client.expire(key, ttl)
            return ToolResult(result=f"Expiry set to {ttl}s on {key!r}")

        else:
            return ToolResult(result=f"[error] unknown operation: {operation!r}")

    except Exception as e:
        return ToolResult(result=f"[error] {e}")
