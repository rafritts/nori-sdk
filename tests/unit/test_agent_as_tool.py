from unittest.mock import AsyncMock, MagicMock, patch


from nori import Agent, Model


def test_agent_has_name():
    agent = Agent(name="Researcher", model=Model(id="grok-4.3", api_key="test-key"), system_prompt="Research things.")
    assert agent.name == "Researcher"


def test_description_falls_back_to_system_prompt():
    agent = Agent(name="Coder", model=Model(id="grok-4.3", api_key="test-key"), system_prompt="Write code.")
    assert "Write code." in agent.schema["function"]["description"]


def test_explicit_description_used_when_set():
    agent = Agent(name="Coder", model=Model(id="grok-4.3", api_key="test-key"), system_prompt="Write code.", description="A coding agent.")
    assert agent.schema["function"]["description"] == "A coding agent."


def test_agent_schema_has_reason():
    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"))
    assert "reason" in agent.schema["function"]["parameters"]["required"]


def test_agent_schema_has_task():
    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"))
    assert "task" in agent.schema["function"]["parameters"]["required"]


async def test_agent_callable():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        msg = MagicMock()
        msg.content = "result"
        msg.tool_calls = None
        usage = MagicMock()
        usage.prompt_tokens = 10
        usage.completion_tokens = 5
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[MagicMock(message=msg)], usage=usage)
        )
        MockOpenAI.return_value = mock_client

        agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), system_prompt="Be helpful.")
        result = await agent(task="do something", reason="needed")
        assert result == "result"


async def test_child_agent_has_isolated_history():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        msg = MagicMock()
        msg.content = "child result"
        msg.tool_calls = None
        usage = MagicMock()
        usage.prompt_tokens = 5
        usage.completion_tokens = 3
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[MagicMock(message=msg)], usage=usage)
        )
        MockOpenAI.return_value = mock_client

        parent = Agent(name="Orchestrator", model=Model(id="grok-4.3", api_key="test-key"))
        parent._history = [{"role": "user", "content": "parent history"}]

        await parent(task="subtask", reason="delegating")
        # Parent history should not contain child's messages
        assert all(m["content"] != "child result" for m in parent._history if "content" in m)
