"""
Retail Systems Demo — End-to-End Return Merchandise Authorization (RMA) Pipeline

Two agents collaborate across a Redis message queue backed by PostgreSQL to process
customer return requests. The ReturnProcessor acts as a judge, making binding decisions
based on customer tier, fraud score, return history, product policy, and stated reason.

Decision outcomes demonstrated:
  Scenario 1 — REFUND        : Gold-tier customer, shipping damage on laptop, valid 20% discount code
  Scenario 2 — EXCHANGE      : Silver-tier customer, wrong-size sweater, expired discount code
  Scenario 3 — ESCALATE_FRAUD: Bronze-tier customer, fraud score 0.81, 4 prior returns in 60 days

Architecture:
  IntakeAgent      reads the return request, validates customer/order/discount against
                   PostgreSQL, creates a pending DB record, and enqueues to Redis.

  ReturnProcessor  dequeues from Redis, loads full context (tier, fraud score, return
                   history, product restockability, return window, discount validity),
                   reasons about the request, writes the decision back to PostgreSQL,
                   and enqueues the result.

Environment variables (defaults match docker-compose.yml):
  RETAIL_DB_DSN     postgresql://nori:nori@localhost:5432/nori_retail
  RETAIL_REDIS_URL  redis://localhost:6379
"""

import asyncio
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

import asyncpg
import redis.asyncio as aioredis

from nori import Agent
from nori.audit import AuditLogger
from nori.tool import tool

# ── Docker Compose ─────────────────────────────────────────────────────────────

_COMPOSE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def compose_up() -> None:
    subprocess.run(["docker", "compose", "up", "-d"], cwd=_COMPOSE_DIR, check=True)


def compose_down() -> None:
    subprocess.run(["docker", "compose", "down", "--volumes"], cwd=_COMPOSE_DIR, check=True)


# ── Config ─────────────────────────────────────────────────────────────────────

DB_DSN     = os.getenv("RETAIL_DB_DSN",    "postgresql://nori:nori@localhost:5432/nori_retail")
REDIS_URL  = os.getenv("RETAIL_REDIS_URL", "redis://localhost:6379")
INTAKE_Q   = "rma:intake"
RESULTS_Q  = "rma:results"
AUDIT_FILE = "logs/retail_demo.audit.log"

# Module-level singletons — set in main() before any agent runs
_pool:  asyncpg.Pool   | None = None
_redis: aioredis.Redis | None = None


# ── Schema ─────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id               SERIAL       PRIMARY KEY,
    name             VARCHAR(100) NOT NULL,
    email            VARCHAR(100) UNIQUE NOT NULL,
    membership_tier  VARCHAR(20)  NOT NULL DEFAULT 'bronze',  -- bronze | silver | gold | platinum
    fraud_score      FLOAT        NOT NULL DEFAULT 0.0,        -- 0.0 = clean, 1.0 = high risk
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
    id                  SERIAL        PRIMARY KEY,
    sku                 VARCHAR(50)   UNIQUE NOT NULL,
    name                VARCHAR(200)  NOT NULL,
    category            VARCHAR(50)   NOT NULL,
    unit_price          DECIMAL(10,2) NOT NULL,
    is_restockable      BOOLEAN       NOT NULL DEFAULT TRUE,
    return_policy_days  INT           NOT NULL DEFAULT 30
);

CREATE TABLE IF NOT EXISTS orders (
    id           SERIAL        PRIMARY KEY,
    customer_id  INT           NOT NULL REFERENCES customers(id),
    order_date   TIMESTAMPTZ   NOT NULL,
    total_amount DECIMAL(10,2) NOT NULL,
    status       VARCHAR(20)   NOT NULL DEFAULT 'delivered'  -- pending | shipped | delivered | cancelled
);

CREATE TABLE IF NOT EXISTS order_items (
    id          SERIAL        PRIMARY KEY,
    order_id    INT           NOT NULL REFERENCES orders(id),
    product_id  INT           NOT NULL REFERENCES products(id),
    quantity    INT           NOT NULL DEFAULT 1,
    unit_price  DECIMAL(10,2) NOT NULL,
    subtotal    DECIMAL(10,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS discount_codes (
    code         VARCHAR(50)   PRIMARY KEY,
    discount_pct DECIMAL(5,2)  NOT NULL,
    valid_from   TIMESTAMPTZ   NOT NULL,
    valid_to     TIMESTAMPTZ   NOT NULL,
    max_uses     INT           NOT NULL DEFAULT 100,
    used_count   INT           NOT NULL DEFAULT 0,
    is_active    BOOLEAN       NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS return_requests (
    id               SERIAL        PRIMARY KEY,
    order_id         INT           NOT NULL REFERENCES orders(id),
    order_item_id    INT           NOT NULL REFERENCES order_items(id),
    customer_id      INT           NOT NULL REFERENCES customers(id),
    stated_reason    TEXT          NOT NULL,
    discount_code    VARCHAR(50)   REFERENCES discount_codes(code),
    status           VARCHAR(30)   NOT NULL DEFAULT 'pending',  -- pending | approved_refund | approved_exchange | escalated_fraud | rejected
    agent_decision   VARCHAR(30),                                -- REFUND | EXCHANGE | ESCALATE_FRAUD | REJECT
    agent_reasoning  TEXT,
    refund_amount    DECIMAL(10,2),
    created_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    processed_at     TIMESTAMPTZ
);
"""


# ── Seed data ──────────────────────────────────────────────────────────────────

async def seed(pool: asyncpg.Pool) -> None:
    """Wipe and repopulate all test data. Safe to call on every run."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "TRUNCATE return_requests, discount_codes, order_items, orders, products, customers "
                "RESTART IDENTITY CASCADE"
            )

            await conn.execute("""
                INSERT INTO customers (name, email, membership_tier, fraud_score) VALUES
                ('Alice Chen',   'alice@example.com', 'gold',   0.05),
                ('Bob Martinez', 'bob@example.com',   'silver', 0.22),
                ('Carol White',  'carol@example.com', 'bronze', 0.81)
            """)

            await conn.execute("""
                INSERT INTO products (sku, name, category, unit_price, is_restockable, return_policy_days) VALUES
                ('LP-GAMING-001', 'Gaming Laptop Pro X1',                'Electronics', 1299.99, TRUE,  30),
                ('AP-WOOL-002',   'Merino Wool Sweater (Navy, L)',        'Clothing',      89.99, TRUE,  60),
                ('HP-WIRE-003',   'Wireless Noise-Cancelling Headphones', 'Electronics',  249.99, TRUE,  30),
                ('GF-MUG-004',    'Custom Engraved Ceramic Mug',          'Gifts',          34.99, FALSE, 14)
            """)

            # Active orders — all within their return windows
            await conn.execute("""
                INSERT INTO orders (customer_id, order_date, total_amount, status) VALUES
                (1, NOW() - INTERVAL '15 days', 1299.99, 'delivered'),  -- id=1  Alice: laptop
                (2, NOW() - INTERVAL '20 days',   89.99, 'delivered'),  -- id=2  Bob: sweater
                (3, NOW() - INTERVAL '5 days',   249.99, 'delivered')   -- id=3  Carol: headphones
            """)

            await conn.execute("""
                INSERT INTO order_items (order_id, product_id, quantity, unit_price, subtotal) VALUES
                (1, 1, 1, 1299.99, 1299.99),  -- id=1  Alice's laptop
                (2, 2, 1,   89.99,   89.99),  -- id=2  Bob's sweater
                (3, 3, 1,  249.99,  249.99)   -- id=3  Carol's headphones
            """)

            # Carol's prior order history (4 returns in 60 days triggers fraud escalation)
            await conn.execute("""
                INSERT INTO orders (customer_id, order_date, total_amount, status) VALUES
                (3, NOW() - INTERVAL '58 days',  34.99, 'delivered'),   -- id=4
                (3, NOW() - INTERVAL '43 days',  89.99, 'delivered'),   -- id=5
                (3, NOW() - INTERVAL '23 days', 249.99, 'delivered'),   -- id=6
                (3, NOW() - INTERVAL '10 days',  89.99, 'delivered')    -- id=7
            """)

            await conn.execute("""
                INSERT INTO order_items (order_id, product_id, quantity, unit_price, subtotal) VALUES
                (4, 4, 1,  34.99,  34.99),   -- id=4
                (5, 2, 1,  89.99,  89.99),   -- id=5
                (6, 3, 1, 249.99, 249.99),   -- id=6
                (7, 2, 1,  89.99,  89.99)    -- id=7
            """)

            await conn.execute("""
                INSERT INTO return_requests
                    (order_id, order_item_id, customer_id, stated_reason,
                     status, agent_decision, agent_reasoning, processed_at)
                VALUES
                    (4, 4, 3, 'Item arrived broken',
                     'approved_refund',   'REFUND',   'First return, damage confirmed by photos',      NOW() - INTERVAL '55 days'),
                    (5, 5, 3, 'Wrong item shipped',
                     'approved_exchange', 'EXCHANGE', 'Merchant fulfillment error, exchange granted',  NOW() - INTERVAL '40 days'),
                    (6, 6, 3, 'Product does not match listing',
                     'approved_refund',   'REFUND',   'Listing inaccuracy confirmed by catalog team',  NOW() - INTERVAL '20 days'),
                    (7, 7, 3, 'Changed my mind, want a different color',
                     'approved_exchange', 'EXCHANGE', 'Within return window, standard exchange',       NOW() - INTERVAL '8 days')
            """)

            await conn.execute("""
                INSERT INTO discount_codes (code, discount_pct, valid_from, valid_to, max_uses, used_count, is_active) VALUES
                ('GOLD20', 20.00, NOW() - INTERVAL '90 days', NOW() + INTERVAL '90 days', 500, 42, TRUE),
                ('SAVE10', 10.00, NOW() - INTERVAL '90 days', NOW() - INTERVAL '30 days', 200, 87, TRUE),
                ('PLAT30', 30.00, NOW() - INTERVAL '30 days', NOW() + INTERVAL '60 days', 100,  5, TRUE)
            """)


# ── Startup helpers ────────────────────────────────────────────────────────────

async def connect_postgres(dsn: str, retries: int = 15, delay: float = 2.0) -> asyncpg.Pool:
    for attempt in range(retries):
        try:
            pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
            await pool.execute("SELECT 1")
            return pool
        except Exception as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"PostgreSQL unavailable after {retries} attempts: {exc}") from exc
            await asyncio.sleep(delay)


async def connect_redis(url: str, retries: int = 15, delay: float = 2.0) -> aioredis.Redis:
    for attempt in range(retries):
        try:
            r = aioredis.from_url(url, decode_responses=True)
            await r.ping()
            return r
        except Exception as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"Redis unavailable after {retries} attempts: {exc}") from exc
            await asyncio.sleep(delay)


# ── Tools ──────────────────────────────────────────────────────────────────────

@tool(summarize_output=False)
async def get_customer(customer_id: int) -> str:
    """Fetch a customer's full profile: name, membership tier, fraud score, and tenure."""
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, name, email, membership_tier, fraud_score, created_at "
            "FROM customers WHERE id = $1",
            customer_id,
        )
    if not row:
        return f"ERROR: Customer #{customer_id} not found."
    return (
        f"Customer #{row['id']}: {row['name']} <{row['email']}>\n"
        f"  Membership tier : {row['membership_tier'].upper()}\n"
        f"  Fraud score     : {row['fraud_score']:.2f}  (0.00 = clean, 1.00 = high risk)\n"
        f"  Member since    : {row['created_at'].strftime('%Y-%m-%d')}"
    )


@tool(summarize_output=False)
async def get_order(order_id: int) -> str:
    """
    Fetch a full order with all line items and product details.
    Includes return-window status and restockability for each item.
    """
    async with _pool.acquire() as conn:
        order = await conn.fetchrow(
            "SELECT id, customer_id, order_date, total_amount, status FROM orders WHERE id = $1",
            order_id,
        )
        if not order:
            return f"ERROR: Order #{order_id} not found."

        items = await conn.fetch(
            """
            SELECT
                oi.id                                                           AS item_id,
                p.id                                                            AS product_id,
                p.sku,
                p.name                                                          AS product_name,
                p.category,
                oi.quantity,
                oi.unit_price,
                oi.subtotal,
                p.is_restockable,
                p.return_policy_days,
                EXTRACT(DAY FROM NOW() - o.order_date)::INT                    AS days_since_order,
                (NOW() - o.order_date <= p.return_policy_days * INTERVAL '1 day') AS within_return_window
            FROM order_items oi
            JOIN products p ON p.id = oi.product_id
            JOIN orders   o ON o.id = oi.order_id
            WHERE oi.order_id = $1
            """,
            order_id,
        )

    days_old = items[0]["days_since_order"] if items else "?"
    lines = [
        f"Order #{order['id']}",
        f"  Customer : #{order['customer_id']}",
        f"  Placed   : {order['order_date'].strftime('%Y-%m-%d')}  ({days_old} days ago)",
        f"  Total    : ${order['total_amount']:,.2f}",
        f"  Status   : {order['status'].upper()}",
        "",
        "  Line items:",
    ]
    for item in items:
        window = (
            f"within {item['return_policy_days']}-day return window"
            if item["within_return_window"]
            else f"OUTSIDE {item['return_policy_days']}-day return window — ineligible"
        )
        restockable = "restockable" if item["is_restockable"] else "NON-RESTOCKABLE (no exchanges)"
        lines.append(
            f"    Item #{item['item_id']} — {item['product_name']}  [{item['sku']}]\n"
            f"      Category  : {item['category']}\n"
            f"      Price     : ${item['unit_price']:,.2f} × {item['quantity']} = ${item['subtotal']:,.2f}\n"
            f"      Policy    : {window}\n"
            f"      Stock     : {restockable}"
        )
    return "\n".join(lines)


@tool(summarize_output=False)
async def validate_discount_code(code: str) -> str:
    """
    Check whether a discount code is valid, active, and within its validity window.
    Returns the discount percentage if valid, or a specific reason if not.
    """
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT code, discount_pct, valid_from, valid_to, max_uses, used_count, is_active "
            "FROM discount_codes WHERE code = $1",
            code.upper(),
        )
    if not row:
        return f"INVALID: Code '{code}' does not exist."

    now = datetime.now(timezone.utc)
    if not row["is_active"]:
        return f"INVALID: Code '{code}' has been deactivated."
    if now < row["valid_from"]:
        return f"NOT YET ACTIVE: Code '{code}' becomes valid on {row['valid_from'].strftime('%Y-%m-%d')}."
    if now > row["valid_to"]:
        return (
            f"EXPIRED: Code '{code}' expired on {row['valid_to'].strftime('%Y-%m-%d')}. "
            f"No discount applies."
        )
    if row["used_count"] >= row["max_uses"]:
        return f"EXHAUSTED: Code '{code}' has reached its {row['max_uses']}-use limit."

    return (
        f"VALID: Code '{code}' — {row['discount_pct']:.0f}% bonus store credit on refunds.\n"
        f"  Valid through : {row['valid_to'].strftime('%Y-%m-%d')}\n"
        f"  Uses          : {row['used_count']} of {row['max_uses']}"
    )


@tool(summarize_output=False)
async def get_return_history(customer_id: int, days: int = 90) -> str:
    """
    Fetch a customer's return request history within the last N days.
    Returns count, dates, products, and decisions — used to detect abuse patterns.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                rr.id,
                rr.created_at,
                rr.stated_reason,
                rr.status,
                rr.agent_decision,
                p.name AS product_name,
                p.category
            FROM return_requests rr
            JOIN order_items oi ON oi.id = rr.order_item_id
            JOIN products    p  ON p.id  = oi.product_id
            WHERE rr.customer_id = $1
              AND rr.created_at >= $2
            ORDER BY rr.created_at DESC
            """,
            customer_id,
            cutoff,
        )

    if not rows:
        return f"No return requests for customer #{customer_id} in the last {days} days."

    lines = [f"Return history for customer #{customer_id} — last {days} days: {len(rows)} request(s)\n"]
    for r in rows:
        decision = r["agent_decision"] or r["status"]
        lines.append(
            f"  #{r['id']}  {r['created_at'].strftime('%Y-%m-%d')}  {r['product_name']} ({r['category']})\n"
            f"       Reason   : {r['stated_reason']}\n"
            f"       Decision : {decision}"
        )
    return "\n".join(lines)


@tool(summarize_output=False)
async def create_return_request(
    order_id: int,
    order_item_id: int,
    customer_id: int,
    stated_reason: str,
    discount_code: str = "",
) -> str:
    """
    Insert a pending return request into the database.
    Returns the new return_request_id — include this in the enqueued payload.
    """
    code = discount_code.upper() if discount_code else None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO return_requests
                (order_id, order_item_id, customer_id, stated_reason, discount_code)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, created_at
            """,
            order_id, order_item_id, customer_id, stated_reason, code,
        )
    return (
        f"Return request #{row['id']} created (status: pending).\n"
        f"  Order #{order_id}  |  Item #{order_item_id}  |  Customer #{customer_id}\n"
        f"  Discount code : {code or 'none'}\n"
        f"  Created       : {row['created_at'].strftime('%Y-%m-%d %H:%M UTC')}"
    )


@tool(summarize_output=False)
async def update_return_decision(
    return_request_id: int,
    decision: str,
    reasoning: str,
    refund_amount: float = 0.0,
) -> str:
    """
    Write the final RMA decision to the database.

    decision must be exactly one of: REFUND, EXCHANGE, ESCALATE_FRAUD, REJECT
    reasoning must be a clear, complete explanation suitable for the customer record.
    refund_amount is the total dollar value returned to the customer (only for REFUND decisions).
    """
    valid = {"REFUND", "EXCHANGE", "ESCALATE_FRAUD", "REJECT"}
    if decision not in valid:
        return f"ERROR: '{decision}' is not a valid decision. Must be one of: {', '.join(sorted(valid))}."

    status_map = {
        "REFUND":         "approved_refund",
        "EXCHANGE":       "approved_exchange",
        "ESCALATE_FRAUD": "escalated_fraud",
        "REJECT":         "rejected",
    }

    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE return_requests
            SET
                agent_decision  = $2,
                agent_reasoning = $3,
                refund_amount   = $4,
                status          = $5,
                processed_at    = NOW()
            WHERE id = $1
            RETURNING id, status, refund_amount, processed_at
            """,
            return_request_id,
            decision,
            reasoning,
            float(refund_amount) if decision == "REFUND" else None,
            status_map[decision],
        )

    if not row:
        return f"ERROR: Return request #{return_request_id} not found."

    refund_line = f"  Refund amount : ${row['refund_amount']:,.2f}\n" if row["refund_amount"] else ""
    return (
        f"Return request #{row['id']} → {decision}\n"
        f"{refund_line}"
        f"  Status     : {row['status']}\n"
        f"  Processed  : {row['processed_at'].strftime('%Y-%m-%d %H:%M UTC')}"
    )


@tool(summarize_output=False)
async def enqueue(queue: str, payload: str) -> str:
    """Push a JSON payload to a named Redis queue (FIFO)."""
    depth = await _redis.rpush(queue, payload)
    return f"Enqueued to '{queue}'. Queue depth: {depth}."


@tool(summarize_output=False)
async def dequeue(queue: str) -> str:
    """
    Pop and return the next message from a named Redis queue.
    Returns a formatted key-value breakdown of the JSON payload, or EMPTY if the queue is empty.
    """
    raw = await _redis.lpop(queue)
    if raw is None:
        return f"EMPTY: No messages in '{queue}'."
    try:
        data = json.loads(raw)
        lines = [f"Dequeued from '{queue}':"]
        for k, v in data.items():
            lines.append(f"  {k}: {v}")
        return "\n".join(lines)
    except (json.JSONDecodeError, TypeError):
        return f"Dequeued from '{queue}' (raw): {raw}"


# ── Agent factories ────────────────────────────────────────────────────────────

def make_intake_agent() -> Agent:
    agent = Agent(
        name="IntakeAgent",
        system_prompt=(
            "You are a retail returns intake specialist. When given a return request, you must:\n"
            "1. Verify the customer exists.\n"
            "2. Verify the order exists and belongs to that customer (check customer_id matches).\n"
            "3. Confirm the specific order item is in that order.\n"
            "4. If a discount code is provided, validate it and note the discount_pct (0 if invalid/expired).\n"
            "5. Create a return request record in the database.\n"
            "6. Enqueue the request to the intake queue as a JSON object with these exact fields:\n"
            "     return_request_id, customer_id, order_id, order_item_id,\n"
            "     stated_reason, discount_code, discount_pct\n"
            "   Set discount_pct to 0 if no valid code. Set discount_code to empty string if none.\n"
            "7. Confirm what was submitted, including whether the discount code is valid.\n"
        ),
        tools=[get_customer, get_order, validate_discount_code, create_return_request, enqueue],
        max_turns=12,
    )
    agent.narration = True
    return agent


def make_processor_agent() -> Agent:
    agent = Agent(
        name="ReturnProcessor",
        system_prompt=(
            "You are a retail return authorization processor. You make binding decisions on return requests.\n"
            "For each request:\n"
            "1. Dequeue the next request from the intake queue.\n"
            "2. Load the customer's profile (tier and fraud score).\n"
            "3. Pull return history for the last 60 days.\n"
            "4. Load the full order details (product, restockability, return window).\n"
            "5. If discount_pct > 0 in the payload, verify the code is still valid.\n"
            "6. Apply these decision rules in order:\n"
            "   a. If fraud_score >= 0.70 OR return count in last 60 days >= 4 → ESCALATE_FRAUD\n"
            "   b. Else if item is outside the return window → REJECT\n"
            "   c. Else if item is NON-RESTOCKABLE and reason is preference/fit/regret → REJECT\n"
            "   d. Else if reason clearly indicates defect, damage, or wrong item shipped → REFUND\n"
            "      If REFUND and discount code is valid: refund_amount = item_price + (discount_pct/100 * item_price)\n"
            "      as bonus store credit on top of the standard refund.\n"
            "   e. Else if reason is size/fit/preference → EXCHANGE\n"
            "7. Record the decision with thorough reasoning.\n"
            "8. Enqueue the result to the results queue as JSON:\n"
            "     return_request_id, customer_name, product_name, decision, refund_amount, reasoning_summary\n"
            "9. State your final decision and the key factors that determined it.\n"
        ),
        tools=[
            dequeue, get_customer, get_return_history, get_order,
            validate_discount_code, update_return_decision, enqueue,
        ],
        max_turns=20,
    )
    agent.narration = True
    return agent


# ── Scenarios ─────────────────────────────────────────────────────────────────

SCENARIOS = [
    {
        "title": "SCENARIO 1 — Shipping damage on a laptop  (expected: REFUND + 20% store credit bonus)",
        "intake_task": (
            "Process this return request:\n"
            "  Customer     : #1 (Alice Chen)\n"
            "  Order        : #1\n"
            "  Item         : #1 (Gaming Laptop Pro X1)\n"
            "  Reason       : 'The laptop arrived with a shattered screen. The outer box had a large "
            "puncture mark and was visibly crushed on one corner — clearly caused by the carrier. "
            "The screen has a crack running from the top-left corner to the center. The unit is "
            "completely unusable.'\n"
            "  Discount code: GOLD20\n"
        ),
    },
    {
        "title": "SCENARIO 2 — Wrong size, preference return  (expected: EXCHANGE, expired code ignored)",
        "intake_task": (
            "Process this return request:\n"
            "  Customer     : #2 (Bob Martinez)\n"
            "  Order        : #2\n"
            "  Item         : #2 (Merino Wool Sweater)\n"
            "  Reason       : 'I ordered a Large but it runs extremely small — it fits more like a "
            "Medium. I need to exchange it for an XL. I have not worn it, tags are still attached.'\n"
            "  Discount code: SAVE10\n"
        ),
    },
    {
        "title": "SCENARIO 3 — High-frequency returner, elevated fraud score  (expected: ESCALATE_FRAUD)",
        "intake_task": (
            "Process this return request:\n"
            "  Customer     : #3 (Carol White)\n"
            "  Order        : #3\n"
            "  Item         : #3 (Wireless Noise-Cancelling Headphones)\n"
            "  Reason       : 'The headphones stopped working completely after a single day of normal "
            "use. The left ear cut out first, then both ears went silent. I tried all troubleshooting "
            "steps in the manual with no result. The unit appears to be defective.'\n"
            "  Discount code: (none)\n"
        ),
    },
]


# ── Main ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    global _pool, _redis

    DIVIDER = "=" * 64

    print(DIVIDER)
    print("Nori retail systems demo — RMA pipeline")
    print(DIVIDER)

    print("\nStarting services...")
    compose_up()

    try:
        print("\nConnecting to services...")
        _pool  = await connect_postgres(DB_DSN)
        _redis = await connect_redis(REDIS_URL)
        print("  PostgreSQL  ✓")
        print("  Redis       ✓")

        print("\nBootstrapping schema and seed data...")
        await _pool.execute(SCHEMA)
        await seed(_pool)
        await _redis.delete(INTAKE_Q, RESULTS_Q)
        print("  Schema created, data seeded, queues cleared.\n")

        auditor = AuditLogger(AUDIT_FILE)

        for i, scenario in enumerate(SCENARIOS, 1):
            print(f"\n{DIVIDER}")
            print(scenario["title"])
            print(DIVIDER)

            intake = make_intake_agent()
            intake.auditor = auditor
            intake_result = await intake.run(scenario["intake_task"])
            print(f"\nIntakeAgent: {intake_result}")

            processor = make_processor_agent()
            processor.auditor = auditor
            processor_result = await processor.run(
                f"Process the next return request from the '{INTAKE_Q}' queue and record your decision."
            )
            print(f"\nReturnProcessor: {processor_result}")

        # Final state summary
        print(f"\n{DIVIDER}")
        print("FINAL STATE — return_requests")
        print(DIVIDER)
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    rr.id,
                    c.name            AS customer,
                    c.membership_tier AS tier,
                    p.name            AS product,
                    rr.agent_decision AS decision,
                    rr.refund_amount,
                    rr.status,
                    rr.processed_at
                FROM return_requests rr
                JOIN customers  c  ON c.id  = rr.customer_id
                JOIN order_items oi ON oi.id = rr.order_item_id
                JOIN products   p  ON p.id  = oi.product_id
                WHERE rr.agent_decision IS NOT NULL
                ORDER BY rr.id DESC
                LIMIT 10
                """
            )
        print(f"  {'#':<4} {'Customer':<16} {'Tier':<8} {'Decision':<16} {'Refund':>10}  Product")
        print(f"  {'-'*4} {'-'*16} {'-'*8} {'-'*16} {'-'*10}  {'-'*30}")
        for row in rows:
            refund = f"${row['refund_amount']:>9,.2f}" if row["refund_amount"] else f"{'—':>10}"
            print(
                f"  {row['id']:<4} {row['customer']:<16} {row['tier']:<8} "
                f"{row['decision']:<16} {refund}  {row['product']}"
            )

        auditor.close()
        await _pool.close()
        await _redis.aclose()
    finally:
        print("\nStopping services...")
        compose_down()


asyncio.run(main())
