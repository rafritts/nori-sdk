from nori.agent import Agent
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.code_runner import CodeRunner


@tool
async def CodeRunnerAgent(task: str) -> ToolResult:
    """Execute iterative Python coding tasks in an isolated sub-agent context window."""
    sub = Agent(
        name="CodeRunnerAgent",
        system_prompt=(
            "You are a Python execution agent. Write and run code to complete the task. "
            "When done, respond with a concise structured summary for the calling agent: "
            "what the code did, the key results or computed values, and any errors encountered."
        ),
        tools=[CodeRunner],
    )
    return ToolResult(result=await sub.run(task))
