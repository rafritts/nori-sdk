from nori.agent import Agent
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.json_read import JsonRead


_SYSTEM_PROMPT = """\
You are a JSON analysis agent. Read the requested files and complete the task, then
respond with a concise structured summary for the calling agent:
- Which files were read and their top-level structure
- The specific values or data extracted (exact, not paraphrased)
- Any missing keys, parse errors, or unexpected structure found
"""


@tool
async def JsonReadAgent(task: str) -> ToolResult:
    """Read and analyze JSON files in an isolated sub-agent context window.
    Use for tasks that require reading multiple JSON files or extracting complex
    nested data across several queries."""
    sub = Agent(name="JsonReadAgent", system_prompt=_SYSTEM_PROMPT, tools=[JsonRead])
    return ToolResult(result=await sub.run(task))
