from nori.agent import Agent
from nori.tool import tool
from nori.tools.web_client import WebClient


@tool
async def WebAgent(task: str) -> str:
    """Perform multi-step web interaction in an isolated sub-agent context window."""
    sub = Agent(name="WebAgent", tools=[WebClient])
    return await sub.run(task)
