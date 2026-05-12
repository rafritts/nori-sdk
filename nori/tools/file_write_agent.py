from nori.agent import Agent
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.file_write import FileWrite


_SYSTEM_PROMPT = """\
You are a file writing agent. Write the requested files, then respond with a
concise structured summary for the calling agent:
- Which files were written and their paths
- A brief description of what was written to each file
- Any files that could not be written and why
"""


@tool
async def FileWriteAgent(task: str) -> ToolResult:
    """Write one or more files in an isolated sub-agent context window. Use for
    multi-file generation tasks."""
    sub = Agent(name="FileWriteAgent", system_prompt=_SYSTEM_PROMPT, tools=[FileWrite])
    return ToolResult(result=await sub.run(task))
