from nori.agent import Agent
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.git import Git


_SYSTEM_PROMPT = """\
You are a git workflow agent. Execute the requested git operations, then respond
with a concise structured summary for the calling agent:
- Which operations were performed (status, commit, push, etc.) and their outcomes
- Current branch and any relevant state changes (new commits, branch created, etc.)
- Any errors or conflicts encountered
"""


@tool
async def GitAgent(task: str) -> ToolResult:
    """Run a multi-step git workflow in an isolated sub-agent context window.
    Use for tasks that require several git operations in sequence."""
    sub = Agent(name="GitAgent", system_prompt=_SYSTEM_PROMPT, tools=[Git])
    return ToolResult(result=await sub.run(task))
