"""
MongoDB Demo — Blog Content Management

An agent manages a blog platform backed by MongoDB. It queries articles,
publishes new content, and updates engagement metrics — all through natural
language backed by the Mongo tool.

Architecture:
  A single BlogAgent equipped with the Mongo tool operates on two collections:
    authors  — contributor profiles
    posts    — articles with tags, status, and engagement metrics

Scenarios:
  1 — Find top-performing published posts tagged 'machine-learning'
  2 — Publish a new post authored by an existing contributor
  3 — Update engagement metrics after a post goes viral on HackerNews

Environment variables (defaults match docker-compose.yml):
  MONGO_DSN  mongodb://nori:nori@localhost:27018/nori_blog?authSource=admin
"""

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: F401 — runs nori.configure()

from motor.motor_asyncio import AsyncIOMotorClient

from nori import Agent
from nori.tools.mongo import Mongo

# ── Docker Compose ─────────────────────────────────────────────────────────────

_COMPOSE_DIR = os.path.dirname(os.path.abspath(__file__))


def compose_up() -> None:
    subprocess.run(["docker", "compose", "up", "-d"], cwd=_COMPOSE_DIR, check=True)


def compose_down() -> None:
    subprocess.run(["docker", "compose", "down", "--volumes"], cwd=_COMPOSE_DIR, check=True)


# ── Config ─────────────────────────────────────────────────────────────────────

DSN = os.getenv("MONGO_DSN", "mongodb://nori:nori@localhost:27018/nori_blog?authSource=admin")

# ── Seed data ──────────────────────────────────────────────────────────────────

def _days_ago(n: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=n)


async def seed(client: AsyncIOMotorClient) -> None:
    db = client.get_default_database()

    await db.authors.drop()
    await db.posts.drop()

    authors = await db.authors.insert_many([
        {
            "slug":        "ada-lovelace",
            "name":        "Ada Lovelace",
            "email":       "ada@example.com",
            "bio":         "Staff engineer and ML systems architect. Writing about inference, scale, and the messy realities of production AI.",
            "posts_count": 12,
            "joined_at":   _days_ago(730),
        },
        {
            "slug":        "grace-hopper",
            "name":        "Grace Hopper",
            "email":       "grace@example.com",
            "bio":         "Distributed systems engineer. Obsessed with databases, consensus protocols, and making complexity legible.",
            "posts_count": 8,
            "joined_at":   _days_ago(540),
        },
        {
            "slug":        "alan-turing",
            "name":        "Alan Turing",
            "email":       "alan@example.com",
            "bio":         "AI researcher exploring the theory and practice of large language models.",
            "posts_count": 5,
            "joined_at":   _days_ago(365),
        },
    ])
    ada_id, grace_id, alan_id = authors.inserted_ids

    await db.posts.insert_many([
        {
            "title":          "Introduction to Vector Databases",
            "slug":           "intro-vector-databases",
            "author_id":      ada_id,
            "author_name":    "Ada Lovelace",
            "tags":           ["databases", "machine-learning", "embeddings"],
            "status":         "published",
            "views":          4821,
            "comments_count": 37,
            "published_at":   _days_ago(45),
            "created_at":     _days_ago(47),
            "summary":        "A practical guide to vector search, similarity metrics, and choosing between Pinecone, Weaviate, and pgvector.",
        },
        {
            "title":          "Fine-Tuning LLMs on a Budget",
            "slug":           "fine-tuning-llms-budget",
            "author_id":      ada_id,
            "author_name":    "Ada Lovelace",
            "tags":           ["machine-learning", "llm", "fine-tuning", "cost"],
            "status":         "published",
            "views":          9103,
            "comments_count": 82,
            "published_at":   _days_ago(18),
            "created_at":     _days_ago(20),
            "summary":        "LoRA, QLoRA, and PEFT techniques that let you fine-tune a 7B model on a single A100 for under $50.",
        },
        {
            "title":          "Consensus Without the PhD: Raft Explained",
            "slug":           "raft-explained",
            "author_id":      grace_id,
            "author_name":    "Grace Hopper",
            "tags":           ["distributed-systems", "databases", "consensus"],
            "status":         "published",
            "views":          3240,
            "comments_count": 19,
            "published_at":   _days_ago(60),
            "created_at":     _days_ago(62),
            "summary":        "A plain-language walkthrough of the Raft consensus algorithm, with animated diagrams.",
        },
        {
            "title":          "Postgres at 10 Million Rows: What Changes",
            "slug":           "postgres-10m-rows",
            "author_id":      grace_id,
            "author_name":    "Grace Hopper",
            "tags":           ["databases", "postgres", "performance"],
            "status":         "published",
            "views":          11450,
            "comments_count": 94,
            "published_at":   _days_ago(90),
            "created_at":     _days_ago(93),
            "summary":        "Index strategies, vacuum tuning, and query plan gotchas that only surface at scale.",
        },
        {
            "title":          "Attention Is All You Need — Annotated",
            "slug":           "attention-annotated",
            "author_id":      alan_id,
            "author_name":    "Alan Turing",
            "tags":           ["machine-learning", "transformers", "research"],
            "status":         "published",
            "views":          6677,
            "comments_count": 55,
            "published_at":   _days_ago(30),
            "created_at":     _days_ago(32),
            "summary":        "A line-by-line walkthrough of the original transformer paper with PyTorch implementations.",
        },
        {
            "title":          "Why Your ML Pipeline Fails in Production",
            "slug":           "ml-pipeline-production-failures",
            "author_id":      ada_id,
            "author_name":    "Ada Lovelace",
            "tags":           ["machine-learning", "mlops", "production"],
            "status":         "published",
            "views":          2134,
            "comments_count": 28,
            "published_at":   _days_ago(8),
            "created_at":     _days_ago(10),
            "summary":        "Data drift, schema mismatches, and the silent failures that tank model performance after deployment.",
        },
        {
            "title":          "CRDTs: Building Conflict-Free Distributed State",
            "slug":           "crdts-conflict-free-state",
            "author_id":      grace_id,
            "author_name":    "Grace Hopper",
            "tags":           ["distributed-systems", "databases"],
            "status":         "draft",
            "views":          0,
            "comments_count": 0,
            "published_at":   None,
            "created_at":     _days_ago(2),
            "summary":        "How conflict-free replicated data types enable eventually-consistent systems without coordination.",
        },
    ])

    await db.posts.create_index([("tags", 1)])
    await db.posts.create_index([("status", 1), ("views", -1)])
    await db.posts.create_index([("slug", 1)], unique=True)


# ── Startup helpers ────────────────────────────────────────────────────────────

async def connect(dsn: str, retries: int = 15, delay: float = 2.0) -> AsyncIOMotorClient:
    for attempt in range(retries):
        try:
            client = AsyncIOMotorClient(dsn, serverSelectionTimeoutMS=3000)
            await client.admin.command("ping")
            return client
        except Exception as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"MongoDB unavailable after {retries} attempts: {exc}") from exc
            await asyncio.sleep(delay)


# ── Scenarios ─────────────────────────────────────────────────────────────────

SCENARIOS = [
    (
        "TOP POSTS BY TAG",
        "Find all published posts tagged 'machine-learning'. Sort them by views descending. "
        "For each post, show the title, author, view count, comment count, and how many days "
        "ago it was published. Report how many qualifying posts exist in total."
    ),
    (
        "PUBLISH NEW POST",
        "Alan Turing just submitted a new post. Publish it with the following details:\n"
        "  title:      'RAG in Production: Lessons Learned'\n"
        "  slug:       'rag-in-production'\n"
        "  author:     Alan Turing (author_name: 'Alan Turing')\n"
        "  tags:       ['machine-learning', 'rag', 'llm', 'production']\n"
        "  status:     'published'\n"
        "  summary:    'Hard-won lessons from deploying retrieval-augmented generation "
        "systems at scale: chunking strategies, reranking, latency budgets, and eval.'\n"
        "  Set views and comments_count to 0, published_at and created_at to now.\n"
        "After inserting, verify the post exists by finding it by slug."
    ),
    (
        "VIRAL POST UPDATE",
        "The post 'Introduction to Vector Databases' (slug: 'intro-vector-databases') was just "
        "featured on the HackerNews front page. Update it to add 8,400 views and 23 new comments "
        "to its existing counts. Then retrieve the post to confirm the final view count and "
        "comment count are correct."
    ),
]


# ── Main ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    DIVIDER = "=" * 64

    print(DIVIDER)
    print("Nori MongoDB demo — blog content management")
    print(DIVIDER)

    print("\nStarting services...")
    compose_up()

    os.environ["MONGO_DSN"] = DSN

    try:
        print("\nConnecting...")
        client = await connect(DSN)
        print("  MongoDB ✓")

        print("\nSeeding collections...")
        await seed(client)
        client.close()
        print("  Done.\n")

        agent = Agent(
            name="BlogAgent",
            system_prompt=(
                "You are a blog content management agent with access to a MongoDB database. "
                "The database has two collections:\n\n"
                "  authors: slug, name, email, bio, posts_count, joined_at\n"
                "  posts:   title, slug, author_id, author_name, tags (array), status "
                "(published|draft), views, comments_count, published_at, created_at, summary\n\n"
                "When querying posts, use the 'find' operation with a filter dict. "
                "To match a tag, use {'tags': 'machine-learning'} — MongoDB matches against arrays automatically. "
                "To sort, note that the find operation returns up to `limit` documents; "
                "for sorted results use a query that filters precisely and rely on the limit. "
                "When updating view/comment counts, use $inc in the update dict: "
                "{'$inc': {'views': N, 'comments_count': M}}. "
                "When inserting posts, set published_at and created_at to the current ISO datetime string."
            ),
            tools=[Mongo],
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
