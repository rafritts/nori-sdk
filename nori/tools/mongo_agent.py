from nori.agent import Agent
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.mongo import Mongo

_SYSTEM_PROMPT = """\
You are a MongoDB database agent. Execute the requested database operations, then respond
with a concise structured summary for the calling agent:
- Documents found, inserted, updated, or deleted
- Collection and field information where relevant
- Any errors encountered
"""


@tool
async def MongoAgent(task: str) -> ToolResult:
    """Run a multi-step MongoDB workflow in an isolated sub-agent context window.
    Use for tasks that require several database operations in sequence."""
    sub = Agent(name="MongoAgent", system_prompt=_SYSTEM_PROMPT, tools=[Mongo])
    return ToolResult(result=await sub.run(task))
