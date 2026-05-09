"""
Extreme demo: multi-agent parallel code review.

An orchestrator dispatches three specialist sub-agents in a single turn —
SecurityReviewer, PerformanceReviewer, and CorrectnessReviewer — each
analyzing a PR diff independently and in parallel. The orchestrator then
synthesizes their findings into a structured review report.

Demonstrates:
  - Parallel sub-agent dispatch (three agents called in one LLM turn)
  - B3 trace propagation: one trace_id flows across all four agents
  - Narration with call_id correlation across concurrent sub-agent calls
  - Full audit trail covering the entire review pipeline
  - Orchestrator-level synthesis from independent specialist inputs

Bugs planted in the PR diff:
  get_user_by_id()      — SQL injection via f-string query
  find_users_with_tag() — N+1 query (one DB call per user)
  paginate()            — off-by-one (1-indexed page not accounted for)
  delete_user()         — rowcount >= 0 always True (catches zero-row deletes)
"""

import asyncio
import textwrap

from nori import Agent, Model, Provider
from nori.audit import AuditLogger
from nori.tool import tool

DIFF_PATH = "/tmp/nori_extreme_review.diff"
AUDIT_FILE = "logs/extreme_demo.audit.log"

DIFF_CONTENT = textwrap.dedent("""\
    diff --git a/api/users.py b/api/users.py
    new file mode 100644
    --- /dev/null
    +++ b/api/users.py
    @@ -0,0 +1,40 @@
    +from db import get_connection
    +
    +
    +def get_user_by_id(user_id: str) -> dict | None:
    +    \"\"\"Fetch a single user by ID.\"\"\"
    +    db = get_connection()
    +    query = f"SELECT * FROM users WHERE id = '{user_id}'"
    +    return db.execute(query).fetchone()
    +
    +
    +def find_users_with_tag(db, all_users: list, tag: str) -> list:
    +    \"\"\"Return all users that have the given tag.\"\"\"
    +    result = []
    +    for user in all_users:
    +        rows = db.execute(
    +            "SELECT tag FROM user_tags WHERE user_id = ?", (user["id"],)
    +        ).fetchall()
    +        tags = [r["tag"] for r in rows]
    +        if tag in tags:
    +            result.append(user)
    +    return result
    +
    +
    +def paginate(items: list, page: int, page_size: int) -> list:
    +    \"\"\"Return items for the given 1-indexed page.\"\"\"
    +    start = page * page_size
    +    end = start + page_size
    +    return items[start:end]
    +
    +
    +def delete_user(db, user_id: int) -> bool:
    +    \"\"\"Delete a user. Returns True if the user existed and was removed.\"\"\"
    +    cursor = db.execute(
    +        "DELETE FROM users WHERE id = ?", (user_id,)
    +    )
    +    db.commit()
    +    return cursor.rowcount >= 0
""")


# ── Shared tool: each reviewer reads the same diff ───────────────────────────

@tool(summarize_output=False)
def read_diff() -> str:
    """Read the PR diff under review."""
    with open(DIFF_PATH) as f:
        return f.read()


# ── Orchestrator ──────────────────────────────────────────────────────────────

async def main() -> None:
    with open(DIFF_PATH, "w") as f:
        f.write(DIFF_CONTENT)

    security_reviewer = Agent(
        name="SecurityReviewer",
        model=Model(id="grok-4.3", provider=Provider.XAI),
        description="Reviews code changes for security vulnerabilities.",
        system_prompt=(
            "You are a security engineer. Read the diff and identify security issues: "
            "injection attacks, auth bypasses, unsafe data handling, insecure patterns. "
            "Report each finding with: location, severity (HIGH/MEDIUM/LOW), and a one-line fix."
        ),
        tools=[read_diff],
        max_turns=5,
    )

    performance_reviewer = Agent(
        name="PerformanceReviewer",
        model=Model(id="grok-4.3", provider=Provider.XAI),
        description="Reviews code changes for performance issues.",
        system_prompt=(
            "You are a performance engineer. Read the diff and identify performance issues: "
            "N+1 queries, unnecessary loops, inefficient data structures, missing indexes. "
            "Report each finding with: location, impact, and a one-line fix."
        ),
        tools=[read_diff],
        max_turns=5,
    )

    correctness_reviewer = Agent(
        name="CorrectnessReviewer",
        model=Model(id="grok-4.3", provider=Provider.XAI),
        description="Reviews code changes for logic errors and correctness bugs.",
        system_prompt=(
            "You are a correctness-focused engineer. Read the diff and identify logic errors: "
            "off-by-one errors, wrong comparisons, incorrect return values, mismatched contracts. "
            "Report each finding with: location, what is wrong, and the correct behavior."
        ),
        tools=[read_diff],
        max_turns=5,
    )

    orchestrator = Agent(
        name="Orchestrator",
        model=Model(id="grok-4.3", provider=Provider.XAI),
        system_prompt=(
            "You are a lead engineer running a code review. "
            "You have three specialist reviewers: SecurityReviewer, PerformanceReviewer, "
            "and CorrectnessReviewer. Dispatch all three in parallel on the PR, "
            "then synthesize their findings into a single structured review report with sections: "
            "Security, Performance, Correctness, and Summary."
        ),
        tools=[security_reviewer, performance_reviewer, correctness_reviewer],
        max_turns=10,
    )
    orchestrator.narration = True
    orchestrator.auditor = AuditLogger(AUDIT_FILE)

    print("=" * 60)
    print("Nori extreme demo — multi-agent parallel code review")
    print("=" * 60)
    print()

    result = await orchestrator.run(
        "Review the PR diff. Dispatch all three reviewers simultaneously, "
        "then produce the final consolidated report."
    )
    orchestrator.auditor.close()

    print(f"\n{'=' * 60}")
    print("REVIEW REPORT")
    print("=" * 60)
    print(result)
    print(f"\nOrchestrator trace_id: {orchestrator.trace_id}")
    print(f"Turns: {orchestrator.turn_count}  |  Cost: ${orchestrator.cost:.4f}")

    import os
    os.unlink(DIFF_PATH)


asyncio.run(main())
