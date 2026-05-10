from nori.agent import Agent
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.bash import Bash


@tool
async def BashAgent(task: str) -> ToolResult:
    """Run a multi-step shell task in an isolated sub-agent context window."""
    sub = Agent(name="BashAgent", tools=[Bash])
    return ToolResult(result=await sub.run(task))
