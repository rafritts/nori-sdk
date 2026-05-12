from nori.agent import Agent
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.csv_read import CsvRead


@tool
async def CsvReadAgent(task: str) -> ToolResult:
    """Read and analyze CSV files in an isolated sub-agent context window.
    Use for tasks that require reading multiple CSV files or cross-file analysis."""
    sub = Agent(name="CsvReadAgent", tools=[CsvRead])
    return ToolResult(result=await sub.run(task))
