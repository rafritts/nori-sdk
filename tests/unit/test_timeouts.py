import asyncio
from unittest.mock import MagicMock, patch

import pytest

from nori import Agent, Model
from nori.exceptions import RunTimeout
from nori.tool import tool


def _make_model():
    return Model(id="test-model", api_key="test-key")


def _make_message(content="Done.", tool_calls=None):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    return msg


# ── tool_timeout ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tool_timeout_returns_error_content():
    """A slow tool returns a timeout message as its result instead of raising."""
    @tool
    async def slow_tool(x: str) -> str:
        """Slow tool."""
        await asyncio.sleep(10)
        return "done"

    agent = Agent(name="T", model=_make_model(), tools=[slow_tool], tool_timeout=0.05)

    call = MagicMock()
    call.id = "call-1"
    call.function.name = "slow_tool"
    call.function.arguments = '{"x": "hi", "reason": "test"}'

    result = await agent._invoke_tool(call)

    assert "ToolTimeout" in result["content"]
    assert result["role"] == "tool"
    assert result["tool_call_id"] == "call-1"


@pytest.mark.asyncio
async def test_fast_tool_not_affected_by_timeout():
    """A tool that completes within the timeout runs normally."""
    @tool
    async def fast_tool(x: str) -> str:
        """Fast tool."""
        return f"got {x}"

    agent = Agent(name="T", model=_make_model(), tools=[fast_tool], tool_timeout=5.0)

    call = MagicMock()
    call.id = "call-1"
    call.function.name = "fast_tool"
    call.function.arguments = '{"x": "hi", "reason": "test"}'

    result = await agent._invoke_tool(call)

    assert result["content"] == "got hi"


# ── run_timeout ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_timeout_raises():
    """agent.run() raises RunTimeout when the run_timeout is exceeded."""
    agent = Agent(name="T", model=_make_model(), run_timeout=0.05)

    async def slow_complete(history):
        await asyncio.sleep(10)
        return _make_message("Done.")

    with patch.object(agent, "_complete", side_effect=slow_complete):
        with pytest.raises(RunTimeout):
            await agent.run("go")


@pytest.mark.asyncio
async def test_run_timeout_none_completes_normally():
    """With no run_timeout, agent.run() completes normally."""
    agent = Agent(name="T", model=_make_model(), run_timeout=None)

    with patch.object(agent, "_complete", return_value=_make_message("Done.")):
        result = await agent.run("go")

    assert result == "Done."


@pytest.mark.asyncio
async def test_run_timeout_message_includes_turn_count():
    """RunTimeout message includes how many turns ran before timing out."""
    agent = Agent(name="T", model=_make_model(), run_timeout=0.05, max_turns=100)

    async def slow_complete(history):
        await asyncio.sleep(10)
        return _make_message("Done.")

    with patch.object(agent, "_complete", side_effect=slow_complete):
        with pytest.raises(RunTimeout, match="run_timeout=0.05s"):
            await agent.run("go")
