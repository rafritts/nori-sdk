from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nori import Agent, Model
from nori.providers import cost_for


def make_text_message(content="Done."):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    return msg


def make_completion_response(
    content="Done.",
    prompt_tokens=10,
    completion_tokens=5,
    reasoning_tokens=0,
    cost_in_usd_ticks=None,
    total_tokens=None,
    cached_tokens=0,
    reasoning_content=None,
):
    msg = make_text_message(content)
    if reasoning_content is not None:
        msg.reasoning_content = reasoning_content
    else:
        msg.reasoning_content = None
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    # Avoid MagicMock auto-attrs being treated as ints.
    if reasoning_tokens:
        details = MagicMock()
        details.reasoning_tokens = reasoning_tokens
        usage.completion_tokens_details = details
    else:
        usage.completion_tokens_details = None
    if cached_tokens:
        pdetails = MagicMock()
        pdetails.cached_tokens = cached_tokens
        usage.prompt_tokens_details = pdetails
    else:
        usage.prompt_tokens_details = None
    usage.total_tokens = (
        total_tokens
        if total_tokens is not None
        else prompt_tokens + completion_tokens + reasoning_tokens
    )
    usage.cost_in_usd_ticks = cost_in_usd_ticks
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
        assert tc["reasoning"] == 0
        assert tc["total"] == 150


async def test_reasoning_tokens_included_in_total():
    """xAI reasoning models put CoT in completion_tokens_details, not completion_tokens."""
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=make_completion_response(
                prompt_tokens=198,
                completion_tokens=4,
                reasoning_tokens=357,
            )
        )
        MockOpenAI.return_value = mock_client
        agent = Agent(name="T", model=Model(id="grok-4-1-fast-reasoning", api_key="test-key"))
        await agent.run("go")
        tc = agent.token_counts
        assert tc["prompt"] == 198
        assert tc["completion"] == 4
        assert tc["reasoning"] == 357
        assert tc["total"] == 559


async def test_cost_prefers_provider_ticks():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        # 10_156_000 ticks = $0.0010156 (1 USD = 1e10 ticks)
        mock_client.chat.completions.create = AsyncMock(
            return_value=make_completion_response(
                prompt_tokens=198,
                completion_tokens=4,
                reasoning_tokens=357,
                cost_in_usd_ticks=10_156_000,
            )
        )
        MockOpenAI.return_value = mock_client
        agent = Agent(name="T", model=Model(id="grok-4-1-fast-reasoning", api_key="test-key"))
        await agent.run("go")
        assert agent.cost == pytest.approx(0.0010156)


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
        assert agent.token_counts == {
            "prompt": 0,
            "completion": 0,
            "reasoning": 0,
            "cached": 0,
            "total": 0,
        }


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
    # Reasoning billed at output rate


async def test_cached_tokens_recorded():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=make_completion_response(
                prompt_tokens=1000,
                completion_tokens=20,
                cached_tokens=800,
            )
        )
        MockOpenAI.return_value = mock_client
        agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"))
        await agent.run("go")
        assert agent.token_counts["cached"] == 800
        assert agent.token_counts["prompt"] == 1000


async def test_conversation_id_sent_as_x_grok_conv_id():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=make_completion_response()
        )
        MockOpenAI.return_value = mock_client
        agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"))
        agent.conversation_id = "chat-abc-123"
        await agent.run("go")
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert kwargs.get("extra_headers") == {"x-grok-conv-id": "chat-abc-123"}


async def test_dynamic_context_appended_after_user_prompt():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=make_completion_response()
        )
        MockOpenAI.return_value = mock_client
        agent = Agent(
            name="T",
            model=Model(id="grok-4.3", api_key="test-key"),
            system_prompt="STATIC SYSTEM",
        )
        agent.dynamic_context = "<current_datetime>Tuesday</current_datetime>"
        await agent.run("hello user")
        messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "STATIC SYSTEM"}
        assert messages[1] == {"role": "user", "content": "hello user"}
        assert messages[2]["role"] == "user"
        assert "current_datetime" in messages[2]["content"]


async def test_reasoning_content_echoed_in_history():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=make_completion_response(
                content="Hi",
                reasoning_content="thinking hard",
            )
        )
        MockOpenAI.return_value = mock_client
        agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"))
        await agent.run("go")
        asst = [m for m in agent.history if m.get("role") == "assistant"]
        assert asst
        assert asst[0].get("reasoning_content") == "thinking hard"
    cost = cost_for("grok-4-1-fast-reasoning", 0, 0, reasoning_tokens=1_000_000)
    assert cost == pytest.approx(0.50)
