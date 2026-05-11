from nori.agent import Agent
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.api_client import ApiClient


@tool
async def WebAgent(task: str) -> ToolResult:
    """Perform multi-step web interaction in an isolated sub-agent context window."""
    sub = Agent(name="WebAgent", tools=[ApiClient])
    return ToolResult(result=await sub.run(task))
