from nori.agent import Agent
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.file_search import FileSearch


@tool
async def FileSearchAgent(task: str) -> ToolResult:
    """Search and reason across files in an isolated sub-agent context window."""
    sub = Agent(name="FileSearchAgent", model=FileSearchAgent.model, tools=[FileSearch])
    return ToolResult(result=await sub.run(task))


FileSearchAgent.model = None
