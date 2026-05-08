def make_modify_tools(agent):
    """Return self-modify-tier meta-tools bound to `agent`."""
    from nori.tool import tool

    @tool(summarize_output=False)
    def add_tool(tool_name: str) -> str:
        """Placeholder: request a tool be added to the agent by name."""
        return f"Tool '{tool_name}' requested (requires orchestrator support)."

    @tool(summarize_output=False)
    def remove_tool(tool_name: str) -> str:
        """Remove a tool from the agent by name."""
        if tool_name in agent._tools:
            del agent._tools[tool_name]
            return f"Tool '{tool_name}' removed."
        return f"Tool '{tool_name}' not found."

    return [add_tool, remove_tool]
