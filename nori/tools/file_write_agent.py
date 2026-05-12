from nori.agent import Agent
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.file_write import FileWrite


@tool
async def FileWriteAgent(task: str) -> ToolResult:
    """Write one or more files in an isolated sub-agent context window. Use for
    multi-file generation tasks."""
    sub = Agent(name="FileWriteAgent", tools=[FileWrite])
    return ToolResult(result=await sub.run(task))
