from nori.agent import Agent
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.bash import Bash


_SYSTEM_PROMPT = """\
You are a shell execution agent. Run commands to complete the task, then respond
with a concise structured summary for the calling agent:
- What commands were run and why
- Key output or results (relevant values, not raw log dumps)
- Any errors or unexpected findings
"""


@tool
async def BashAgent(task: str) -> ToolResult:
    """Run a multi-step shell task in an isolated sub-agent context window."""
    sub = Agent(name="BashAgent", system_prompt=_SYSTEM_PROMPT, tools=[Bash])
    return ToolResult(result=await sub.run(task))
