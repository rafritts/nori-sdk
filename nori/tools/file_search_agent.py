import nori.config as config
from nori.agent import Agent
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.file_search import FileSearch


@tool
async def FileSearchAgent(task: str) -> ToolResult:
    """Search and reason across files in an isolated sub-agent context window."""
    _d = config.get_defaults()
    model = _d.tool_models.get(FileSearchAgent) or _d.model
    sub = Agent(
        name="FileSearchAgent",
        model=model,
        system_prompt=(
            "You are a file search agent. Search for the requested files or patterns, "
            "then respond with a concise structured summary for the calling agent: "
            "the matching file paths, relevant line numbers or snippets, and a note "
            "if nothing was found or the search was ambiguous."
        ),
        tools=[FileSearch],
    )
    return ToolResult(result=await sub.run(task))
