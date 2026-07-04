import json
import os

try:
    from motor.motor_asyncio import AsyncIOMotorDatabase
    from motor.motor_asyncio import AsyncIOMotorClient
except ImportError:
    raise ImportError(
        "motor is required for the Mongo tool. "
        "Install it with: uv add motor (or `nori-sdk[mongo]`)"
    )

from nori.tool import tool
from nori.tools.base import ToolResult

_clients: dict[str, AsyncIOMotorClient] = {}


def _db(dsn: str = "") -> AsyncIOMotorDatabase:
    dsn = dsn or os.environ["MONGO_DSN"]
    if dsn not in _clients:
        _clients[dsn] = AsyncIOMotorClient(dsn)
    return _clients[dsn].get_default_database()


def _serialize(docs: list) -> str:
    if not docs:
        return "(no documents)"
    return json.dumps(docs, default=str)


@tool
async def Mongo(
    operation: str,
    collection: str = "",
    filter: dict = None,
    document: dict = None,
    update: dict = None,
    limit: int = 10,
    dsn: str = "",
) -> ToolResult:
    """Interact with a MongoDB database. Operations:
    - find: query documents in a collection (pass filter dict and limit)
    - insert: insert a document into a collection
    - update: update documents matching a filter (pass filter and update dicts)
    - delete: delete documents matching a filter
    - collections: list all collections in the database
    """
    try:
        db = _db(dsn)
    except KeyError:
        return ToolResult(result=(
            "[error] MONGO_DSN not set. Set it via: export MONGO_DSN=mongodb://..., "
            "add it to .env, or pass dsn='...' directly to the tool call."
        ))
    except Exception as e:
        return ToolResult(result=f"[error] connection failed: {e}")

    op = operation.lower()

    try:
        if op == "collections":
            names = await db.list_collection_names()
            return ToolResult(result="\n".join(sorted(names)) or "(no collections)")

        if not collection:
            return ToolResult(result=f"[error] operation {operation!r} requires collection")

        col = db[collection]

        if op == "find":
            cursor = col.find(filter or {}, {"_id": 0}, limit=limit)
            docs = await cursor.to_list(length=limit)
            return ToolResult(result=_serialize(docs))

        elif op == "insert":
            if not document:
                return ToolResult(result="[error] insert requires document")
            result = await col.insert_one(document)
            return ToolResult(result=f"Inserted: {result.inserted_id}")

        elif op == "update":
            if not filter or not update:
                return ToolResult(result="[error] update requires filter and update")
            result = await col.update_many(filter, update)
            return ToolResult(result=f"Matched {result.matched_count}, modified {result.modified_count}")

        elif op == "delete":
            if not filter:
                return ToolResult(result="[error] delete requires filter")
            result = await col.delete_many(filter)
            return ToolResult(result=f"Deleted {result.deleted_count} document(s)")

        else:
            return ToolResult(result=f"[error] unknown operation: {operation!r}")

    except Exception as e:
        return ToolResult(result=f"[error] {e}")
