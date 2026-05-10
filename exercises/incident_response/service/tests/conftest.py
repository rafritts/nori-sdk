import pytest, sqlite3, tempfile, os, sys

# Add service to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

SERVICE_DIR = os.path.join(os.path.dirname(__file__), "..")


@pytest.fixture(scope="session")
def db_path(tmp_path_factory):
    db_file = tmp_path_factory.mktemp("db") / "test.db"
    schema = open(os.path.join(SERVICE_DIR, "schema.sql")).read()
    conn = sqlite3.connect(str(db_file))
    conn.executescript(schema)
    # Seed: 5 customers, 200 orders (40 per customer), 2 items per order
    for i in range(1, 6):
        conn.execute(
            "INSERT INTO customers (id, name, email) VALUES (?, ?, ?)",
            (i, f"Customer {i}", f"customer{i}@example.com")
        )
    order_id = 1
    for customer_id in range(1, 6):
        for j in range(40):
            conn.execute(
                "INSERT INTO orders (id, customer_id, product, amount) VALUES (?, ?, ?, ?)",
                (order_id, customer_id, f"Product {j}", 10.0 + j)
            )
            for k in range(2):
                conn.execute(
                    "INSERT INTO order_items (order_id, sku, quantity, price) VALUES (?, ?, ?, ?)",
                    (order_id, f"SKU-{j}-{k}", k+1, 5.0)
                )
            order_id += 1
    conn.commit()
    conn.close()
    return str(db_file)


@pytest.fixture(autouse=True)
def patch_pool(db_path):
    import db as db_module
    from db import ConnectionPool, POOL_SIZE
    old_pool = db_module._pool
    db_module._pool = ConnectionPool(db_path, POOL_SIZE)
    yield
    db_module._pool = old_pool
