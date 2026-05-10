def make_custodian_tools(agent):
    """Return custodian-tier meta-tools bound to `agent`."""
    from nori.tool import tool

    @tool(summarize_output=False)
    def update_system_prompt(new_prompt: str) -> str:
        """Update the agent's system prompt mid-run."""
        agent.system_prompt = new_prompt
        return "System prompt updated."

    @tool(summarize_output=False)
    def get_system_prompt() -> str:
        """Return the current system prompt."""
        return agent.system_prompt

    return [update_system_prompt, get_system_prompt]
