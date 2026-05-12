"""
Redis Demo — Feature Flag Management

An agent manages a live feature flag system backed by Redis. Flags control
which product features are active, with support for permanent toggles and
time-boxed rollouts via TTL.

Architecture:
  A single FeatureFlagAgent equipped with the Redis tool reads and writes
  flags as Redis keys. Permanent flags have no expiry; timed rollouts use
  TTL so they expire automatically.

  Key schema:
    feature:{name}        → "enabled" | "disabled"
    feature:{name}:tier   → "all" | "beta" | "internal"  (optional metadata)

Scenarios:
  1 — Audit current flag state: list all flags and report which are enabled
  2 — Apply a release plan: enable, disable, and schedule timed rollouts
  3 — Pre-launch check: verify critical flags, report TTLs on timed flags

Environment variables (defaults match docker-compose.yml):
  REDIS_DSN  redis://localhost:6380
"""

import asyncio
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: F401 — runs nori.configure()

import redis.asyncio as aioredis

from nori import Agent
from nori.tools.redis import Redis

# ── Docker Compose ─────────────────────────────────────────────────────────────

_COMPOSE_DIR = os.path.dirname(os.path.abspath(__file__))


def compose_up() -> None:
    subprocess.run(["docker", "compose", "up", "-d"], cwd=_COMPOSE_DIR, check=True)


def compose_down() -> None:
    subprocess.run(["docker", "compose", "down", "--volumes"], cwd=_COMPOSE_DIR, check=True)


# ── Config ─────────────────────────────────────────────────────────────────────

DSN = os.getenv("REDIS_DSN", "redis://localhost:6380")

# ── Seed data ──────────────────────────────────────────────────────────────────

async def seed(r: aioredis.Redis) -> None:
    await r.flushdb()

    flags = {
        "feature:checkout_v2":         "enabled",
        "feature:checkout_v2:tier":    "all",
        "feature:dark_mode":           "enabled",
        "feature:dark_mode:tier":      "all",
        "feature:ai_search":           "disabled",
        "feature:ai_search:tier":      "beta",
        "feature:new_dashboard":       "disabled",
        "feature:new_dashboard:tier":  "internal",
        "feature:multi_currency":      "disabled",
        "feature:multi_currency:tier": "all",
        "feature:loyalty_points":      "enabled",
        "feature:loyalty_points:tier": "beta",
        "feature:social_login":        "enabled",
        "feature:social_login:tier":   "all",
        "feature:bulk_export":         "disabled",
        "feature:bulk_export:tier":    "internal",
    }
    for key, value in flags.items():
        await r.set(key, value)

    # Simulate a timed rollout already in progress (expires in ~2 hours)
    await r.setex("feature:holiday_banner",      7200, "enabled")
    await r.set("feature:holiday_banner:tier",   "all")


# ── Startup helpers ────────────────────────────────────────────────────────────

async def connect(dsn: str, retries: int = 15, delay: float = 2.0) -> aioredis.Redis:
    for attempt in range(retries):
        try:
            r = aioredis.from_url(dsn, decode_responses=True)
            await r.ping()
            return r
        except Exception as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"Redis unavailable after {retries} attempts: {exc}") from exc
            await asyncio.sleep(delay)


# ── Scenarios ─────────────────────────────────────────────────────────────────

SCENARIOS = [
    (
        "FLAG AUDIT",
        "Audit all feature flags. List every flag (keys matching 'feature:*' but not ':tier' keys), "
        "its current value (enabled/disabled), and its TTL if it has one. Group results into "
        "Enabled, Disabled, and Timed Rollouts (those with a TTL). Report the total count in each group."
    ),
    (
        "APPLY RELEASE PLAN",
        "Apply the following release plan:\n"
        "  1. Enable 'feature:ai_search' permanently.\n"
        "  2. Enable 'feature:new_dashboard' for a 4-hour timed rollout (14400 seconds).\n"
        "  3. Enable 'feature:multi_currency' permanently.\n"
        "  4. Disable 'feature:loyalty_points' immediately.\n"
        "  5. Disable 'feature:bulk_export' immediately.\n"
        "After applying all changes, confirm the new state of each affected flag, "
        "including TTL where applicable."
    ),
    (
        "PRE-LAUNCH CHECK",
        "Run a pre-launch verification. Confirm that these critical flags are in the correct state:\n"
        "  - feature:checkout_v2    must be ENABLED\n"
        "  - feature:ai_search      must be ENABLED\n"
        "  - feature:multi_currency must be ENABLED\n"
        "  - feature:dark_mode      must be ENABLED\n"
        "  - feature:social_login   must be ENABLED\n"
        "For any timed rollouts currently active, report the remaining TTL. "
        "Give a clear GO / NO-GO verdict with a summary of any issues found."
    ),
]


# ── Main ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    DIVIDER = "=" * 64

    print(DIVIDER)
    print("Nori Redis demo — feature flag management")
    print(DIVIDER)

    print("\nStarting services...")
    compose_up()

    os.environ["REDIS_DSN"] = DSN

    try:
        print("\nConnecting...")
        r = await connect(DSN)
        print("  Redis ✓")

        print("\nSeeding flag data...")
        await seed(r)
        await r.aclose()
        print("  Done.\n")

        agent = Agent(
            name="FeatureFlagAgent",
            system_prompt=(
                "You are a feature flag management agent with access to a Redis instance. "
                "Feature flags are stored as Redis string keys with the pattern 'feature:{name}' "
                "and values of 'enabled' or 'disabled'. Optional metadata keys follow the pattern "
                "'feature:{name}:tier' with values like 'all', 'beta', or 'internal'.\n\n"
                "Timed rollouts are flags set with a TTL — they expire automatically. "
                "When reporting TTLs, convert seconds to a human-readable format (e.g. '2h 0m'). "
                "When listing flags, use the 'keys' operation with pattern 'feature:*' and filter "
                "out ':tier' suffix keys to get the primary flag list."
            ),
            tools=[Redis],
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
