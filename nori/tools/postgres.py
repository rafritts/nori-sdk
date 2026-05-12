import json
import os

import asyncpg

from nori.tool import tool
from nori.tools.base import ToolResult

_pools: dict[str, asyncpg.Pool] = {}


async def _pool(dsn: str = "") -> asyncpg.Pool:
    dsn = dsn or os.environ["POSTGRES_DSN"]
    if dsn not in _pools:
        _pools[dsn] = await asyncpg.create_pool(dsn)
    return _pools[dsn]


def _rows(rows: list[asyncpg.Record]) -> str:
    if not rows:
        return "(no rows)"
    return json.dumps([dict(r) for r in rows], default=str)


@tool
async def Postgres(
    operation: str,
    query: str = "",
    params: list = None,
    table: str = "",
    dsn: str = "",
) -> ToolResult:
    """Interact with a PostgreSQL database. Operations:
    - query: run a SELECT and return rows as JSON
    - execute: run INSERT/UPDATE/DELETE and return affected row count
    - schema: list tables (no args) or describe a table's columns (pass table name)
    """
    try:
        pool = await _pool(dsn)
    except KeyError:
        return ToolResult(result="[error] POSTGRES_DSN not set")
    except Exception as e:
        return ToolResult(result=f"[error] connection failed: {e}")

    op = operation.lower()

    if op == "query":
        if not query:
            return ToolResult(result="[error] query requires a SQL string")
        try:
            rows = await pool.fetch(query, *(params or []))
            return ToolResult(result=_rows(rows))
        except Exception as e:
            return ToolResult(result=f"[error] {e}")

    elif op == "execute":
        if not query:
            return ToolResult(result="[error] execute requires a SQL string")
        try:
            status = await pool.execute(query, *(params or []))
            return ToolResult(result=status)
        except Exception as e:
            return ToolResult(result=f"[error] {e}")

    elif op == "schema":
        try:
            if table:
                rows = await pool.fetch(
                    """
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = $1
                    ORDER BY ordinal_position
                    """,
                    table,
                )
            else:
                rows = await pool.fetch(
                    """
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                    ORDER BY table_name
                    """
                )
            return ToolResult(result=_rows(rows))
        except Exception as e:
            return ToolResult(result=f"[error] {e}")

    else:
        return ToolResult(result=f"[error] unknown operation: {operation!r}")
