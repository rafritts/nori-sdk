from nori.agent import Agent
from nori.tool import tool
from nori.tools.file_search import FileSearch


@tool
async def FileSearchAgent(task: str) -> str:
    """Search and reason across files in an isolated sub-agent context window."""
    sub = Agent(name="FileSearchAgent", model=FileSearchAgent.model, tools=[FileSearch])
    return await sub.run(task)


FileSearchAgent.model = None
