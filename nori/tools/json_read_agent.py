from nori.agent import Agent
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.json_read import JsonRead


@tool
async def JsonReadAgent(task: str) -> ToolResult:
    """Read and analyze JSON files in an isolated sub-agent context window.
    Use for tasks that require reading multiple JSON files or extracting complex
    nested data across several queries."""
    sub = Agent(name="JsonReadAgent", tools=[JsonRead])
    return ToolResult(result=await sub.run(task))
