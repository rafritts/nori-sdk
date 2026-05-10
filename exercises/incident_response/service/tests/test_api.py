"""
Test suite for the order service.

Some tests FAIL when bugs are present:
  test_cache_stores_and_retrieves   — FAILS when CACHE_TTL=0
  test_query_plan_uses_index        — FAILS when index on orders.customer_id is missing
  test_concurrent_load              — FAILS when db.py has connection leak on error (bug #3)
"""

import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app
import cache


def test_health_check():
    """Health check always returns ok with a valid customer count."""
    result = app.health_check()
    assert result["status"] == "ok"
    assert result["customer_count"] >= 0


def test_get_customer_returns_data():
    """Fetching a known customer returns expected fields."""
    customer = app.get_customer(1)
    assert customer is not None
    assert customer["id"] == 1
    assert "name" in customer
    assert "email" in customer


def test_get_customer_orders_returns_correct_structure():
    """get_customer_orders returns correct structure (data correct, may be slow)."""
    result = app.get_customer_orders(1)
    assert result["customer_id"] == 1
    assert "order_count" in result
    assert "orders" in result
    assert result["order_count"] == len(result["orders"])
    if result["orders"]:
        order = result["orders"][0]
        assert "id" in order
        assert "product" in order
        assert "amount" in order
        assert "items" in order


def test_cache_stores_and_retrieves():
    """Cache set/get round-trip must work — FAILS when CACHE_TTL=0.

    When CACHE_TTL=0 every entry expires immediately (time.time() + 0 <= time.time()),
    so cache.get always returns None after cache.set.
    """
    cache._store.clear()
    cache.set("test_key", {"value": 42})
    result = cache.get("test_key")
    assert result is not None, (
        "Cache returned None immediately after set — CACHE_TTL is likely 0. "
        "Fix: set CACHE_TTL = 300 in cache.py"
    )
    assert result["value"] == 42


def test_query_plan_uses_index(db_path):
    """EXPLAIN QUERY PLAN must show index lookup on orders.customer_id — FAILS when index is missing.

    Without CREATE INDEX idx_orders_customer_id ON orders(customer_id),
    SQLite does a full table scan (SCAN orders) for every customer order lookup.
    Fix: uncomment the CREATE INDEX line in schema.sql.
    """
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM orders WHERE customer_id = ?", (1,)
    ).fetchall()
    conn.close()

    plan_text = " ".join(str(r) for r in rows).upper()
    assert "SCAN ORDERS" not in plan_text or "USING INDEX" in plan_text, (
        f"Query plan shows full table scan: {plan_text}\n"
        "Fix: add CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id) "
        "in schema.sql"
    )


def test_concurrent_load(db_path):
    """Connections must return to pool even when queries raise exceptions — FAILS with bug #3.

    Bug #3: pool.release(conn) is not in a finally block. After N errors equal to pool
    size, all connections are leaked and the pool is exhausted. Subsequent valid queries
    raise RuntimeError: Connection pool exhausted.

    Fix: move pool.release(conn) into a finally block in db.py.
    """
    import db as db_module
    from db import ConnectionPool, execute_query

    test_pool = ConnectionPool(db_path, size=3)
    original = db_module._pool
    db_module._pool = test_pool

    try:
        for _ in range(3):
            try:
                execute_query("SELECT * FROM nonexistent_table_xyz")
            except Exception:
                pass

        # If connections leaked, pool is exhausted and this will raise RuntimeError
        result = execute_query("SELECT COUNT(*) AS cnt FROM customers")
        assert result[0]["cnt"] >= 0, "Valid query must succeed after error recovery"
    finally:
        db_module._pool = original
