def make_mutation_tools(agent):
    """Return self-mutation-tier meta-tools bound to `agent`."""
    from nori.tool import tool

    @tool(summarize_output=False)
    def update_model(new_model: str) -> str:
        """Switch the agent to a different model mid-run."""
        agent.model = new_model
        return f"Model updated to '{new_model}'."

    @tool(summarize_output=False)
    def set_max_turns(n: int) -> str:
        """Update the agent's max_turns limit."""
        agent._max_turns = n
        return f"max_turns set to {n}."

    return [update_model, set_max_turns]
