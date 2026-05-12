"""
Postgres Demo — Inventory Management

An agent manages a product inventory database, answering natural language
questions about stock levels, generating reports, and processing shipments.

Architecture:
  A single InventoryAgent equipped with the Postgres tool writes SQL queries
  against a seeded product catalog to answer each scenario.

Scenarios:
  1 — Identify every product below its reorder threshold, sorted by urgency
  2 — Generate a full inventory value report broken down by category
  3 — Process a weekly shipment: update quantities and confirm new stock levels

Environment variables (defaults match docker-compose.yml):
  POSTGRES_DSN  postgresql://nori:nori@localhost:5433/nori_inventory
"""

import asyncio
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: F401 — runs nori.configure()

import asyncpg

from nori import Agent
from nori.tools.postgres import Postgres

# ── Docker Compose ─────────────────────────────────────────────────────────────

_COMPOSE_DIR = os.path.dirname(os.path.abspath(__file__))


def compose_up() -> None:
    subprocess.run(["docker", "compose", "up", "-d"], cwd=_COMPOSE_DIR, check=True)


def compose_down() -> None:
    subprocess.run(["docker", "compose", "down", "--volumes"], cwd=_COMPOSE_DIR, check=True)


# ── Config ─────────────────────────────────────────────────────────────────────

DSN = os.getenv("POSTGRES_DSN", "postgresql://nori:nori@localhost:5433/nori_inventory")

# ── Schema ─────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id             SERIAL        PRIMARY KEY,
    sku            VARCHAR(50)   UNIQUE NOT NULL,
    name           VARCHAR(200)  NOT NULL,
    category       VARCHAR(50)   NOT NULL,
    supplier       VARCHAR(100)  NOT NULL,
    unit_price     DECIMAL(10,2) NOT NULL,
    quantity       INT           NOT NULL DEFAULT 0,
    reorder_point  INT           NOT NULL DEFAULT 10,
    reorder_qty    INT           NOT NULL DEFAULT 50,
    last_restocked TIMESTAMPTZ
);
"""

# ── Seed data ──────────────────────────────────────────────────────────────────

async def seed(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("TRUNCATE products RESTART IDENTITY")
            await conn.execute("""
                INSERT INTO products
                    (sku, name, category, supplier, unit_price, quantity, reorder_point, reorder_qty)
                VALUES
                    ('ELEC-LAPTOP-001', 'ThinkPad X1 Carbon (Gen 12)',         'Electronics', 'Lenovo Direct',      1299.99,  3, 10, 25),
                    ('ELEC-PHONE-005',  'Google Pixel 8 Pro',                  'Electronics', 'Google Store',        999.99,  7, 15, 30),
                    ('ELEC-TABLET-02',  'iPad Air 5th Gen',                    'Electronics', 'Apple Business',      749.99, 22, 10, 20),
                    ('ELEC-HDPH-009',   'Sony WH-1000XM5 Headphones',          'Electronics', 'Sony B2B',            349.99,  2,  8, 20),
                    ('ELEC-MONIT-004',  'LG 27" 4K UltraFine Display',         'Electronics', 'LG Commercial',       699.99, 11,  8, 16),
                    ('CLOTH-JACKET-003','Arc''teryx Beta AR Jacket (M)',        'Clothing',    'Arc''teryx Pro',      599.99,  5, 10, 15),
                    ('CLOTH-BOOT-011',  'Salomon X Ultra 4 GTX (10)',           'Clothing',    'Salomon Trade',       189.99, 14, 12, 24),
                    ('CLOTH-SHIRT-07',  'Patagonia Organic Cotton Tee (L)',     'Clothing',    'Patagonia B2B',        49.99, 83, 30, 60),
                    ('FOOD-COFFEE-01',  'Intelligentsia Black Cat Espresso',    'Food',        'Intelligentsia',       22.99,  9, 20, 50),
                    ('FOOD-TEA-004',    'Harney & Sons Paris Tea (50ct)',       'Food',        'Harney & Sons',        12.99, 31, 25, 75),
                    ('FOOD-CHOC-008',   'Valrhona Guanaja 70% Dark (3kg)',      'Food',        'Valrhona Pro',         89.99,  0, 10, 20),
                    ('TOOL-DRILL-02',   'DeWalt 20V MAX Drill/Driver Kit',      'Tools',       'DeWalt Pro',          179.99,  0,  5, 10),
                    ('TOOL-SAW-008',    'Milwaukee M18 FUEL Circular Saw',      'Tools',       'Milwaukee Tool',      199.99,  4,  5, 10),
                    ('TOOL-LEVEL-01',   'Stabila 48" Digital Level',            'Tools',       'Stabila USA',          89.99, 16,  6, 12),
                    ('BOOK-DDIA-001',   'Designing Data-Intensive Applications','Books',       'O''Reilly Direct',     49.99, 18, 15, 30),
                    ('BOOK-SICP-002',   'Structure and Interpretation of CPs',  'Books',       'MIT Press',            44.99, 27, 15, 30)
            """)


# ── Startup helpers ────────────────────────────────────────────────────────────

async def connect(dsn: str, retries: int = 15, delay: float = 2.0) -> asyncpg.Pool:
    for attempt in range(retries):
        try:
            pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
            await pool.execute("SELECT 1")
            return pool
        except Exception as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"PostgreSQL unavailable after {retries} attempts: {exc}") from exc
            await asyncio.sleep(delay)


# ── Scenarios ─────────────────────────────────────────────────────────────────

SCENARIOS = [
    (
        "LOW STOCK ALERT",
        "Review the inventory. Identify every product that has fallen below its reorder_point "
        "and sort them by urgency — furthest below their threshold first. Show the SKU, name, "
        "current quantity, reorder point, and how many units short we are."
    ),
    (
        "INVENTORY VALUE REPORT",
        "Generate a full inventory value report. For each category, show the number of distinct "
        "products, total units in stock, and total inventory value (quantity × unit_price). "
        "Include a grand total row at the end."
    ),
    (
        "PROCESS WEEKLY SHIPMENT",
        "We just received our weekly shipment. Update inventory with these quantities received:\n"
        "  ELEC-LAPTOP-001 : +200 units\n"
        "  ELEC-PHONE-005  : +150 units\n"
        "  CLOTH-JACKET-003: +75 units\n"
        "  TOOL-DRILL-02   : +10 units\n"
        "  FOOD-CHOC-008   : +20 units\n"
        "After updating, confirm the new quantity for each SKU and note whether they are "
        "now above or still below their reorder points."
    ),
]


# ── Main ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    DIVIDER = "=" * 64

    print(DIVIDER)
    print("Nori PostgreSQL demo — inventory management")
    print(DIVIDER)

    print("\nStarting services...")
    compose_up()

    os.environ["POSTGRES_DSN"] = DSN

    try:
        print("\nConnecting...")
        pool = await connect(DSN)
        print("  PostgreSQL ✓")

        print("\nBootstrapping schema and seed data...")
        await pool.execute(SCHEMA)
        await seed(pool)
        await pool.close()
        print("  Done.\n")

        agent = Agent(
            name="InventoryAgent",
            system_prompt=(
                "You are an inventory management agent with read/write access to a PostgreSQL "
                "product database. The products table has these columns: id, sku, name, category, "
                "supplier, unit_price, quantity, reorder_point, reorder_qty, last_restocked.\n\n"
                "When updating inventory (shipment arrivals), use UPDATE with parameterized queries "
                "and set last_restocked = NOW(). Always confirm changes by querying back the "
                "updated rows. Present results in clean, readable tables where appropriate."
            ),
            tools=[Postgres],
        )
        agent.narration = True

        for title, task in SCENARIOS:
            print(f"\n{DIVIDER}")
            print(f"SCENARIO — {title}")
            print(DIVIDER)
            print(f"Task: {task}\n")
            result = await agent.run(task)
            print(f"\nAgent: {result}")

    finally:
        print("\nStopping services...")
        compose_down()


asyncio.run(main())
