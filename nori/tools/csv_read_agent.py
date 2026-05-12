from nori.agent import Agent
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.csv_read import CsvRead


_SYSTEM_PROMPT = """\
You are a CSV analysis agent. Read the requested files and complete the task, then
respond with a concise structured summary for the calling agent:
- Which files were read and their shape (rows, columns)
- Key findings, values, or answers extracted from the data
- Any missing data, parse errors, or anomalies noticed
"""


@tool
async def CsvReadAgent(task: str) -> ToolResult:
    """Read and analyze CSV files in an isolated sub-agent context window.
    Use for tasks that require reading multiple CSV files or cross-file analysis."""
    sub = Agent(name="CsvReadAgent", system_prompt=_SYSTEM_PROMPT, tools=[CsvRead])
    return ToolResult(result=await sub.run(task))
