from nori.agent import Agent
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.git import Git


@tool
async def GitAgent(task: str) -> ToolResult:
    """Run a multi-step git workflow in an isolated sub-agent context window.
    Use for tasks that require several git operations in sequence."""
    sub = Agent(name="GitAgent", tools=[Git])
    return ToolResult(result=await sub.run(task))
