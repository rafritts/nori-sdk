from nori.agent import Agent
from nori.tool import tool
from nori.tools.web_client import WebClient


@tool
async def WebSearch(query: str) -> str:
    """Synthesize a web search result using a sub-agent research loop."""
    sub = Agent(
        name="WebSearch",
        system_prompt="You are a research assistant. Use WebClient to fetch pages and synthesize an answer.",
        tools=[WebClient],
    )
    sub.summarize_tool_output = False
    return await sub.run(query)
