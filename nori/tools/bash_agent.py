from nori.agent import Agent
from nori.tool import tool
from nori.tools.bash import Bash


@tool
async def BashAgent(task: str) -> str:
    """Run a multi-step shell task in an isolated sub-agent context window."""
    sub = Agent(name="BashAgent", tools=[Bash])
    sub.summarize_tool_output = False
    return await sub.run(task)
