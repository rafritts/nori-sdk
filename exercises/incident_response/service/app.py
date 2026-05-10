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
    rows = execute_query(
        """
        SELECT o.id, o.product, o.amount, o.status, o.created_at,
               i.id AS item_id, i.sku, i.quantity, i.price
        FROM orders o
        LEFT JOIN order_items i ON i.order_id = o.id
        WHERE o.customer_id = ?
        ORDER BY o.id, i.id
        """,
        (customer_id,)
    )

    orders_dict = {}
    for row in rows:
        oid = row["id"]
        if oid not in orders_dict:
            orders_dict[oid] = {
                "id": row["id"],
                "product": row["product"],
                "amount": row["amount"],
                "status": row["status"],
                "created_at": row["created_at"],
                "items": [],
            }
        if row["item_id"] is not None:
            orders_dict[oid]["items"].append({
                "id": row["item_id"],
                "sku": row["sku"],
                "quantity": row["quantity"],
                "price": row["price"],
            })

    result = list(orders_dict.values())
    response = {"customer_id": customer_id, "order_count": len(result), "orders": result}
    cache.set(cache_key, response)
    return response


def health_check() -> dict:
    rows = execute_query("SELECT COUNT(*) AS cnt FROM customers")
    return {"status": "ok", "customer_count": rows[0]["cnt"]}
