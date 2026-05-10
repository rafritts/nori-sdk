# Post-Mortem: Order Service Outages Due to Connection Pool Exhaustion

## Summary
The order service experienced frequent 503 Service Unavailable errors caused by "Connection pool exhausted" errors under load. This impacted /orders/customer/{id} endpoints.

## Root Causes
1. **BUG #1**: Missing index on `orders(customer_id)` leading to slow full table scans and increased query times.
2. **BUG #2**: N+1 query problem in `get_customer_orders()` — separate query per order for items, amplifying DB load.
3. **BUG #3**: Connection leak in `execute_write()` — connections not released on exceptions, depleting the pool of size 5.
4. **BUG #4**: Cache TTL accidentally set to 0 (from "fix cache invalidation" commit), causing every request to miss cache and hit DB.

## Timeline
- Recent commit reset TTL to 0.
- Increased load exposed pool exhaustion (previous pool size bump from 3 to 5 was insufficient).

## Fixes Applied
- Added index on orders.customer_id.
- Refactored to single JOIN query eliminating N+1.
- Fixed execute_write with try/finally for release.
- Restored CACHE_TTL=300.
- Verified with test suite (all 6 tests pass).

## Prevention
- Add connection pool monitoring and alerts.
- Enforce code review for DB/cache changes.
- Load test before deploys.

## Resolution
Service stabilized after fixes; no more pool exhaustion observed.
