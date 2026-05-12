from nori.agent import Agent
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.file_read import FileRead


@tool
async def FileReadAgent(task: str) -> ToolResult:
    """Read one or more files in an isolated sub-agent context window. Use for
    multi-file reading tasks where the output would overflow the current context."""
    sub = Agent(name="FileReadAgent", tools=[FileRead])
    return ToolResult(result=await sub.run(task))
