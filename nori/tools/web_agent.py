from nori.agent import Agent
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.api_client import ApiClient


_SYSTEM_PROMPT = """\
You are a web interaction agent. Make the requested API calls or web requests, then
respond with a concise structured summary for the calling agent:
- Which endpoints were called and their HTTP status codes
- The key data returned (relevant fields, not full raw responses)
- Any errors, rate limits, or unexpected responses encountered
"""


@tool
async def WebAgent(task: str) -> ToolResult:
    """Perform multi-step web interaction in an isolated sub-agent context window."""
    sub = Agent(name="WebAgent", system_prompt=_SYSTEM_PROMPT, tools=[ApiClient])
    return ToolResult(result=await sub.run(task))
