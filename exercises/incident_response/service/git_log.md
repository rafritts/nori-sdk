commit a3f7d91 (HEAD -> main)
Author: Jamie Chen <jchen@example.com>
Date:   2026-05-09 18:42:11 +0000

    fix cache invalidation on user update

    Cache was returning stale data after user profile updates.
    Reset TTL on set() to ensure fresh data on next request.

commit b8e1c54
Author: Maria Santos <msantos@example.com>
Date:   2026-05-09 14:15:03 +0000

    add order status filter to list endpoint

    Support ?status= query param on GET /orders. Filters applied
    in Python after fetch — index-based filtering to be added later.

commit 3d92a17
Author: Jamie Chen <jchen@example.com>
Date:   2026-05-08 22:07:44 +0000

    increase connection pool size from 3 to 5

    Intermittent pool exhaustion under moderate load. Bumping
    pool size buys headroom while root cause is investigated.

commit f1a08bb
Author: Alex Kim <akim@example.com>
Date:   2026-05-08 11:33:29 +0000

    add order_items table and seed data generator

    New order_items table tracks line items per order. setup.py
    generates 10k orders with 2 items each for load testing.

commit 92c4e30
Author: Maria Santos <msantos@example.com>
Date:   2026-05-07 16:58:02 +0000

    add cache layer to get_customer_orders

    Hot path was hitting DB on every request. Added in-memory
    cache with 300s TTL — measured 40% reduction in DB queries
    during load test.

commit 7bb3021
Author: Alex Kim <akim@example.com>
Date:   2026-05-07 09:14:55 +0000

    add health_check endpoint

    Simple liveness probe: SELECT COUNT(*) FROM customers.
    Returns {"status": "ok", "customer_count": N}.

commit 5e0d14c
Author: Jamie Chen <jchen@example.com>
Date:   2026-05-06 20:31:08 +0000

    switch from single connection to connection pool

    Single global connection was causing serialization under
    concurrent load. Pool of 3 connections with 2s acquire
    timeout. Pool size tunable via POOL_SIZE env var.

commit c2f9a88
Author: Maria Santos <msantos@example.com>
Date:   2026-05-06 13:47:21 +0000

    initial schema: customers and orders tables

    Baseline schema. Indexes to be added once query patterns
    are understood from production traffic.

commit d8e3b7f
Author: Alex Kim <akim@example.com>
Date:   2026-05-05 18:20:33 +0000

    scaffold service: db.py and app.py stubs

    Basic project structure. db.py: SQLite wrapper.
    app.py: business logic layer. No tests yet.

commit 01a4c2e
Author: Jamie Chen <jchen@example.com>
Date:   2026-05-05 10:05:17 +0000

    initial commit: project skeleton

    pyproject.toml, .gitignore, README. Empty service/ dir.
