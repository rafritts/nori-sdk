import sqlite3, os, sys

SERVICE_DIR = os.path.join(os.path.dirname(__file__), "service")
DB_PATH = os.path.join(SERVICE_DIR, "orders.db")
SCHEMA_PATH = os.path.join(SERVICE_DIR, "schema.sql")
SEED_RECORD_PATH = os.path.join(SERVICE_DIR, "seed.sql")


# ── Canonical buggy source files ──────────────────────────────────────────────
# These are restored on every run so the exercise always starts broken.

_BUGGY_CACHE = '''\
import time
from typing import Any

# BUG #4: TTL accidentally zeroed in commit "fix cache invalidation on user update"
# Previous value: 300
CACHE_TTL = 0

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
'''

_BUGGY_DB = '''\
import sqlite3
import queue
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "orders.db")
POOL_SIZE = 5


class ConnectionPool:
    def __init__(self, db_path, size=POOL_SIZE):
        self._pool = queue.Queue(maxsize=size)
        for _ in range(size):
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._pool.put(conn)

    def acquire(self, timeout=2.0):
        try:
            return self._pool.get(timeout=timeout)
        except queue.Empty:
            raise RuntimeError("Connection pool exhausted — too many concurrent requests")

    def release(self, conn):
        self._pool.put(conn)


_pool: ConnectionPool | None = None


def init_pool(db_path=DB_PATH, size=POOL_SIZE):
    global _pool
    _pool = ConnectionPool(db_path, size)


def get_pool():
    global _pool
    if _pool is None:
        init_pool()
    return _pool


def execute_query(sql: str, params=()) -> list:
    pool = get_pool()
    conn = pool.acquire()
    try:
        cursor = conn.execute(sql, params)
        results = cursor.fetchall()
        return [dict(row) for row in results]
    finally:
        pool.release(conn)


def execute_write(sql: str, params=()) -> int:
    # BUG #3: connection not released in finally — leaks on exception
    pool = get_pool()
    conn = pool.acquire()
    cursor = conn.execute(sql, params)
    conn.commit()
    row_id = cursor.lastrowid
    pool.release(conn)
    return row_id
'''

_BUGGY_SCHEMA = '''\
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    created_at TEXT DEFAULT (datetime(\'now\'))
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    product TEXT NOT NULL,
    amount REAL NOT NULL,
    status TEXT DEFAULT \'pending\',
    created_at TEXT DEFAULT (datetime(\'now\')),
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

-- BUG #1: index commented out — causes full table scans on customer order lookups
-- CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id)
);

CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
'''

_BUGGY_APP = '''\
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import cache
from db import execute_query, execute_write


def get_customer(customer_id: int) -> dict | None:
    rows = execute_query("SELECT * FROM customers WHERE id = ?", (customer_id,))
    return rows[0] if rows else None


def list_customers(limit: int = 100) -> list:
    return execute_query("SELECT * FROM customers LIMIT ?", (limit,))


def get_customer_orders(customer_id: int) -> dict:
    cache_key = f"customer:{customer_id}:orders"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # BUG #2: N+1 — one query per order to fetch its items
    orders_rows = execute_query(
        "SELECT id, product, amount, status, created_at FROM orders WHERE customer_id = ? ORDER BY id",
        (customer_id,)
    )

    orders_dict = {}
    for row in orders_rows:
        oid = row["id"]
        orders_dict[oid] = {
            "id": row["id"],
            "product": row["product"],
            "amount": row["amount"],
            "status": row["status"],
            "created_at": row["created_at"],
            "items": [],
        }
        item_rows = execute_query(
            "SELECT id, sku, quantity, price FROM order_items WHERE order_id = ?",
            (oid,)
        )
        for item in item_rows:
            orders_dict[oid]["items"].append({
                "id": item["id"],
                "sku": item["sku"],
                "quantity": item["quantity"],
                "price": item["price"],
            })

    result = list(orders_dict.values())
    response = {"customer_id": customer_id, "order_count": len(result), "orders": result}
    cache.set(cache_key, response)
    return response


def health_check() -> dict:
    rows = execute_query("SELECT COUNT(*) AS cnt FROM customers")
    return {"status": "ok", "customer_count": rows[0]["cnt"]}
'''


def plant_bugs() -> None:
    """Restore all four planted bugs so every run starts from a broken state."""
    files = {
        os.path.join(SERVICE_DIR, "cache.py"): _BUGGY_CACHE,
        os.path.join(SERVICE_DIR, "db.py"): _BUGGY_DB,
        os.path.join(SERVICE_DIR, "schema.sql"): _BUGGY_SCHEMA,
        os.path.join(SERVICE_DIR, "app.py"): _BUGGY_APP,
    }
    for path, content in files.items():
        with open(path, "w") as f:
            f.write(content)
    print("[setup] Bugs planted in service source files.")


def setup():
    plant_bugs()

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    print("[setup] Creating database and seeding...")

    schema = open(SCHEMA_PATH).read()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(schema)

    # Insert 100 customers
    customers = [(i, f"Customer {i}", f"customer{i}@example.com") for i in range(1, 101)]
    conn.executemany("INSERT INTO customers (id, name, email) VALUES (?, ?, ?)", customers)

    # Insert 100 orders per customer = 10k total orders
    orders = []
    items = []
    order_id = 1
    products = ["Widget A", "Widget B", "Gadget Pro", "Service Pack", "Subscription"]
    for customer_id in range(1, 101):
        for j in range(100):
            product = products[j % len(products)]
            orders.append((order_id, customer_id, product, round(9.99 + j * 0.5, 2)))
            items.append((order_id, f"SKU-{j:04d}", 1, round(4.99 + j * 0.25, 2)))
            if j % 3 == 0:
                items.append((order_id, f"SKU-{j:04d}-B", 2, 2.99))
            order_id += 1

    conn.executemany(
        "INSERT INTO orders (id, customer_id, product, amount) VALUES (?, ?, ?, ?)", orders
    )
    conn.executemany(
        "INSERT INTO order_items (order_id, sku, quantity, price) VALUES (?, ?, ?, ?)", items
    )
    conn.commit()
    conn.close()

    with open(SEED_RECORD_PATH, "w") as f:
        f.write(
            f"-- Generated by setup.py: {len(customers)} customers, "
            f"{len(orders)} orders, {len(items)} items\n"
        )
        f.write("-- Applied via Python for performance. Run setup.py to regenerate.\n")

    print(f"[setup] Done: {len(customers)} customers, {len(orders)} orders, {len(items)} order items")
    return DB_PATH


if __name__ == "__main__":
    setup()
