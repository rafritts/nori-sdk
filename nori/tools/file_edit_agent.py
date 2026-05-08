from nori.agent import Agent
from nori.tool import tool
from nori.tools.file_edit import FileEdit
from nori.tools.file_search import FileSearch


@tool
async def FileEditAgent(task: str) -> str:
    """Edit files across multiple paths in an isolated sub-agent context window."""
    sub = Agent(name="FileEditAgent", tools=[FileEdit, FileSearch])
    sub.summarize_tool_output = False
    return await sub.run(task)
