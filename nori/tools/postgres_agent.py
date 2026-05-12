from nori.agent import Agent
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.postgres import Postgres

_SYSTEM_PROMPT = """\
You are a PostgreSQL database agent. Execute the requested database operations, then respond
with a concise structured summary for the calling agent:
- Results of queries or operations performed
- Row counts, affected records, or schema information
- Any errors encountered
"""


@tool
async def PostgresAgent(task: str) -> ToolResult:
    """Run a multi-step PostgreSQL workflow in an isolated sub-agent context window.
    Use for tasks that require several database operations in sequence."""
    sub = Agent(name="PostgresAgent", system_prompt=_SYSTEM_PROMPT, tools=[Postgres])
    return ToolResult(result=await sub.run(task))
