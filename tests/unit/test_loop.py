import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nori import Agent
from nori.exceptions import MaxTurnsExceeded
from nori.tool import tool


def make_text_message(content="Done."):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    return msg


def make_tool_call_message(name, args, call_id="call_1"):
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tc]
    return msg


@tool
def get_weather(city: str) -> str:
    """Get weather."""
    return f"sunny in {city}"


async def test_loop_terminates_without_tool_calls():
    agent = Agent(name="T", model="grok-3")
    agent._complete = AsyncMock(return_value=make_text_message("Hello!"))
    result = await agent.run("Say hi")
    assert result == "Hello!"


async def test_tool_call_dispatched():
    called_with = {}

    @tool
    def spy_tool(city: str) -> str:
        """Spy."""
        called_with["city"] = city
        return "sunny"

    agent = Agent(name="T", model="grok-3", tools=[spy_tool])
    agent._complete = AsyncMock(side_effect=[
        make_tool_call_message("spy_tool", {"city": "Austin", "reason": "checking weather"}),
        make_text_message("It's sunny."),
    ])
    await agent.run("Weather?")
    assert called_with["city"] == "Austin"


async def test_tool_result_appended_to_history():
    @tool
    def my_tool(x: str) -> str:
        """Tool."""
        return "result_value"

    agent = Agent(name="T", model="grok-3", tools=[my_tool])
    agent._complete = AsyncMock(side_effect=[
        make_tool_call_message("my_tool", {"x": "a", "reason": "r"}),
        make_text_message("Done."),
    ])
    await agent.run("Go")
    tool_msgs = [m for m in agent._history if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["content"] == "result_value"


async def test_loop_iterates_until_no_tool_calls():
    @tool
    def noop(x: str) -> str:
        """Noop."""
        return "ok"

    agent = Agent(name="T", model="grok-3", tools=[noop], max_turns=10)
    agent._complete = AsyncMock(side_effect=[
        make_tool_call_message("noop", {"x": "1", "reason": "r"}, "c1"),
        make_tool_call_message("noop", {"x": "2", "reason": "r"}, "c2"),
        make_text_message("Done."),
    ])
    result = await agent.run("Go")
    assert agent._complete.call_count == 3
    assert result == "Done."


async def test_max_turns_raises():
    agent = Agent(name="T", model="grok-3", max_turns=2)
    agent._complete = AsyncMock(return_value=make_text_message("ok"))
    await agent.run("first")
    await agent.run("second")
    with pytest.raises(MaxTurnsExceeded):
        await agent.run("third")


async def test_tools_schemas_passed_to_complete():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=MagicMock(
            choices=[MagicMock(message=make_text_message("ok"))]
        ))
        MockOpenAI.return_value = mock_client

        agent = Agent(name="T", model="grok-3", tools=[get_weather])
        await agent.run("hi")
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "tools" in call_kwargs
        assert call_kwargs["tools"][0]["function"]["name"] == "get_weather"
