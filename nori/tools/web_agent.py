from nori.agent import Agent
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.web_client import WebClient


@tool
async def WebAgent(task: str) -> ToolResult:
    """Perform multi-step web interaction in an isolated sub-agent context window."""
    sub = Agent(name="WebAgent", tools=[WebClient])
    return ToolResult(result=await sub.run(task))
