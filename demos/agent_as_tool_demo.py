"""
Demonstrates agents calling other agents as tools.

Any Agent instance exposes a .schema property and is callable, making it
a first-class tool. An orchestrator can delegate subtasks to specialist
sub-agents without knowing their internals.

Shows:
  1. Two specialist agents (research + writer) wired into an orchestrator
  2. Orchestrator delegates naturally — the model decides when to call each
"""

import asyncio

from nori import Agent
from nori.audit import AuditLogger
from nori.tool import tool

DIVIDER = "=" * 60


# ── Specialist: Researcher ────────────────────────────────────────────────────

@tool
def web_lookup(query: str) -> str:
    """Look up a topic and return a brief factual summary."""
    # Simulated knowledge base
    facts = {
        "python": "Python is a high-level, interpreted language created by Guido van Rossum in 1991.",
        "rust": "Rust is a systems language focused on safety and performance, first released by Mozilla in 2010.",
        "go": "Go (Golang) is a statically typed, compiled language designed at Google, released in 2009.",
    }
    for key, val in facts.items():
        if key in query.lower():
            return val
    return f"No specific data found for: {query}"


researcher = Agent(
    name="Researcher",
    description="Looks up factual information about programming languages.",
    system_prompt="You are a research agent. Use web_lookup to find facts and return them clearly.",
    tools=[web_lookup],
)


# ── Specialist: Writer ────────────────────────────────────────────────────────

@tool
def format_as_markdown(title: str, body: str) -> str:
    """Format a title and body into a markdown document."""
    return f"# {title}\n\n{body}\n"


@tool
def word_count(text: str) -> str:
    """Count the words in a block of text."""
    return str(len(text.split()))


writer = Agent(
    name="Writer",
    description="Formats and edits content into polished markdown documents.",
    system_prompt="You are a writing agent. Format content clearly and check your word counts.",
    tools=[format_as_markdown, word_count],
)


# ── Orchestrator ──────────────────────────────────────────────────────────────

async def main():
    print(DIVIDER)
    print("Nori agent-as-tool demo")
    print(DIVIDER)
    print()

    orchestrator = Agent(
        name="Orchestrator",
        system_prompt=(
            "You are an orchestrator. You have access to a Researcher and a Writer agent. "
            "Delegate research to Researcher and formatting to Writer. "
            "Coordinate them to produce a final polished document."
        ),
        tools=[researcher, writer],
    )
    orchestrator.narration = True
    auditor = AuditLogger("logs/agent_as_tool_demo.audit.log")
    orchestrator.auditor = auditor
    researcher.auditor = auditor
    writer.auditor = auditor

    result = await orchestrator.run(
        "Write a short comparison of Python, Rust, and Go. "
        "Research each language, then have the Writer produce a formatted markdown doc."
    )
    auditor.close()

    print(f"\n{DIVIDER}")
    print("Final output:")
    print(DIVIDER)
    print(result)
    print(f"\nOrchestrator turns: {orchestrator.turn_count}  |  Cost: ${orchestrator.cost:.4f}")


asyncio.run(main())
