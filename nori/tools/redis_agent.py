from nori.agent import Agent
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.redis import Redis

_SYSTEM_PROMPT = """\
You are a Redis cache agent. Execute the requested cache operations, then respond
with a concise structured summary for the calling agent:
- Keys read, written, or deleted and their values
- TTL information where relevant
- Any errors encountered
"""


@tool
async def RedisAgent(task: str) -> ToolResult:
    """Run a multi-step Redis workflow in an isolated sub-agent context window.
    Use for tasks that require several cache operations in sequence."""
    sub = Agent(name="RedisAgent", system_prompt=_SYSTEM_PROMPT, tools=[Redis])
    return ToolResult(result=await sub.run(task))
