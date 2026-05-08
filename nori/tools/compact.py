from nori.tool import tool

COMPACT_TOOL_NAME = "Compact"


@tool(summarize_output=False)
async def Compact() -> str:
    """Voluntarily compact the conversation history. Call this when context is getting long."""
    # The agent loop intercepts this call and handles compaction directly.
    return "compacted"
