from nori.agent import Agent
from nori.tool import tool
from nori.tools.web_client import WebClient


@tool
async def WebAgent(task: str) -> str:
    """Perform multi-step web interaction in an isolated sub-agent context window."""
    sub = Agent(name="WebAgent", model="grok-4.3", tools=[WebClient])
    sub.summarize_tool_output = False
    return await sub.run(task)
