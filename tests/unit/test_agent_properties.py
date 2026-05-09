import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nori import Agent, Model
from nori.providers import cost_for
from nori.tool import tool


def make_text_message(content="Done."):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    return msg


def make_completion_response(content="Done.", prompt_tokens=10, completion_tokens=5):
    msg = make_text_message(content)
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    resp = MagicMock()
    resp.choices = [MagicMock(message=msg)]
    resp.usage = usage
    return resp


def make_agent(mock_client=None):
    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"))
    if mock_client:
        agent.__dict__["_Agent__client"] = mock_client
    return agent


async def test_turn_count_increments():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=make_completion_response()
        )
        MockOpenAI.return_value = mock_client
        agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"))
        await agent.run("go")
        assert agent.turn_count == 1
        await agent.run("go again")
        assert agent.turn_count == 2


async def test_token_counts_returns_dict():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=make_completion_response(prompt_tokens=100, completion_tokens=50)
        )
        MockOpenAI.return_value = mock_client
        agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"))
        await agent.run("go")
        tc = agent.token_counts
        assert "prompt" in tc and "completion" in tc
        assert tc["prompt"] == 100
        assert tc["completion"] == 50


async def test_cost_is_float():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=make_completion_response(prompt_tokens=1000, completion_tokens=500)
        )
        MockOpenAI.return_value = mock_client
        agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"))
        await agent.run("go")
        assert isinstance(agent.cost, float)
        assert agent.cost > 0


def test_history_returns_list():
    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"))
    assert isinstance(agent.history, list)


def test_tool_calls_returns_list():
    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"))
    assert isinstance(agent.tool_calls, list)


async def test_reset_clears_state():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=make_completion_response()
        )
        MockOpenAI.return_value = mock_client
        agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"))
        await agent.run("go")
        assert agent.turn_count > 0
        agent.reset()
        assert agent.turn_count == 0
        assert agent.history == []
        assert agent.token_counts == {"prompt": 0, "completion": 0}


def test_properties_are_read_only():
    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"))
    with pytest.raises(AttributeError):
        agent.history = []
    with pytest.raises(AttributeError):
        agent.turn_count = 0
    with pytest.raises(AttributeError):
        agent.cost = 0.0


def test_model_pricing_lookup():
    cost = cost_for("grok-4.3", 1_000_000, 0)
    assert cost == pytest.approx(1.25)
    cost = cost_for("grok-4.3", 0, 1_000_000)
    assert cost == pytest.approx(2.50)
    cost = cost_for("unknown-model", 1_000_000, 1_000_000)
    assert cost == 0.0
