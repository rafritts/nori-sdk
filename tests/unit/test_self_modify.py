import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nori import Agent, Model, SelfModify


def make_tool_call_message(name, args, call_id="c1"):
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tc]
    return msg


def make_text_message(content="Done."):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    return msg


def test_custodian_false_by_default():
    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"))
    assert "update_system_prompt" not in agent._tools


def test_custodian_unlocks_update_system_prompt():
    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), self_modify=SelfModify.CUSTODIAN)
    assert "update_system_prompt" in agent._tools


def test_self_modify_additive():
    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), self_modify=SelfModify.MODIFY)
    assert "update_system_prompt" in agent._tools
    assert "add_tool" in agent._tools


def test_self_mutation_additive():
    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), self_modify=SelfModify.MUTATION)
    assert "update_system_prompt" in agent._tools
    assert "add_tool" in agent._tools
    assert "update_model" in agent._tools


async def test_update_system_prompt_changes_system_prompt():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=[
            MagicMock(choices=[MagicMock(message=make_tool_call_message(
                "update_system_prompt",
                {"new_prompt": "New instructions.", "reason": "updating"},
            ))], usage=MagicMock(prompt_tokens=5, completion_tokens=3)),
            MagicMock(choices=[MagicMock(message=make_text_message())],
                      usage=MagicMock(prompt_tokens=5, completion_tokens=3)),
        ])
        MockOpenAI.return_value = mock_client

        agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), self_modify=SelfModify.CUSTODIAN)
        await agent.run("update the prompt")
        assert agent.system_prompt == "New instructions."
