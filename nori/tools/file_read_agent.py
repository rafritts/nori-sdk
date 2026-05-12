from nori.agent import Agent
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.file_read import FileRead


_SYSTEM_PROMPT = """\
You are a file reading agent. Read the requested files and complete the task, then
respond with a concise structured summary for the calling agent:
- Which files were read
- The relevant content or answers extracted (include exact values, not paraphrases)
- Any files that were missing or unreadable
"""


@tool
async def FileReadAgent(task: str) -> ToolResult:
    """Read one or more files in an isolated sub-agent context window. Use for
    multi-file reading tasks where the output would overflow the current context."""
    sub = Agent(name="FileReadAgent", system_prompt=_SYSTEM_PROMPT, tools=[FileRead])
    return ToolResult(result=await sub.run(task))
