from nori.agent import Agent
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.file_edit import FileEdit
from nori.tools.file_search import FileSearch


_SYSTEM_PROMPT = """\
You are a file editing agent. Apply the requested changes, then respond with a
concise structured summary for the calling agent:
- Which files were modified and what changed in each
- Any files that could not be edited and why
- Confirmation that changes are complete
"""


@tool
async def FileEditAgent(task: str) -> ToolResult:
    """Edit files across multiple paths in an isolated sub-agent context window."""
    sub = Agent(name="FileEditAgent", system_prompt=_SYSTEM_PROMPT, tools=[FileEdit, FileSearch])
    return ToolResult(result=await sub.run(task))
