import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nori import Agent, Model
from nori.agent import _is_duplicate_assistant_prose
from nori.exceptions import MaxTurnsExceeded
from nori.tool import tool


def make_text_message(content="Done."):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    return msg


def make_tool_call_message(name, args, call_id="call_1", content=None):
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = [tc]
    return msg


@tool
def get_weather(city: str) -> str:
    """Get weather."""
    return f"sunny in {city}"


async def test_loop_terminates_without_tool_calls():
    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"))
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

    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), tools=[spy_tool])
    agent._complete = AsyncMock(side_effect=[
        make_tool_call_message("spy_tool", {"city": "Austin", "reason": "checking weather"}),
        make_text_message(""),  # stop calling tools
        make_text_message("It's sunny."),  # forced final-output pass
    ])
    await agent.run("Weather?")
    assert called_with["city"] == "Austin"


async def test_tool_result_appended_to_history():
    @tool
    def my_tool(x: str) -> str:
        """Tool."""
        return "result_value"

    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), tools=[my_tool])
    agent._complete = AsyncMock(side_effect=[
        make_tool_call_message("my_tool", {"x": "a", "reason": "r"}),
        make_text_message(""),
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

    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), tools=[noop], max_turns=10)
    agent._complete = AsyncMock(side_effect=[
        make_tool_call_message("noop", {"x": "1", "reason": "r"}, "c1"),
        make_tool_call_message("noop", {"x": "2", "reason": "r"}, "c2"),
        make_text_message(""),
        make_text_message("Done."),
    ])
    result = await agent.run("Go")
    assert agent._complete.call_count == 4
    assert result == "Done."


async def test_parallel_tools_both_called():
    results = []

    @tool
    def tool_a(x: str) -> str:
        """A."""
        results.append("a")
        return "a"

    @tool
    def tool_b(x: str) -> str:
        """B."""
        results.append("b")
        return "b"

    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), tools=[tool_a, tool_b])
    tc_a = MagicMock()
    tc_a.id = "c_a"
    tc_a.function.name = "tool_a"
    tc_a.function.arguments = json.dumps({"x": "1", "reason": "r"})
    tc_b = MagicMock()
    tc_b.id = "c_b"
    tc_b.function.name = "tool_b"
    tc_b.function.arguments = json.dumps({"x": "2", "reason": "r"})
    multi = MagicMock()
    multi.content = None
    multi.tool_calls = [tc_a, tc_b]

    agent._complete = AsyncMock(side_effect=[
        multi,
        make_text_message(""),
        make_text_message("done"),
    ])
    await agent.run("go")
    assert "a" in results and "b" in results


async def test_parallel_results_both_appended():
    @tool
    def t1(x: str) -> str:
        """T1."""
        return "r1"

    @tool
    def t2(x: str) -> str:
        """T2."""
        return "r2"

    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), tools=[t1, t2])
    tc1 = MagicMock()
    tc1.id = "c1"
    tc1.function.name = "t1"
    tc1.function.arguments = json.dumps({"x": "a", "reason": "r"})
    tc2 = MagicMock()
    tc2.id = "c2"
    tc2.function.name = "t2"
    tc2.function.arguments = json.dumps({"x": "b", "reason": "r"})
    multi = MagicMock()
    multi.content = None
    multi.tool_calls = [tc1, tc2]

    agent._complete = AsyncMock(side_effect=[
        multi,
        make_text_message(""),
        make_text_message("done"),
    ])
    await agent.run("go")
    tool_msgs = [m for m in agent._history if m.get("role") == "tool"]
    contents = {m["content"] for m in tool_msgs}
    assert contents == {"r1", "r2"}


async def test_max_turns_raises():
    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), max_turns=2)
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

        agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), tools=[get_weather])
        await agent.run("hi")
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "tools" in call_kwargs
        assert call_kwargs["tools"][0]["function"]["name"] == "get_weather"


async def test_require_no_tools_ack_gates_exit():
    """With the gate on, a no-tool reply is not final until NO_TOOL_CALLS."""
    @tool
    def noop(x: str) -> str:
        """Noop."""
        return "ok"

    agent = Agent(
        name="T",
        model=Model(id="grok-4.3", api_key="test-key"),
        tools=[noop],
        require_no_tools_ack=True,
        max_turns=10,
    )
    agent._complete = AsyncMock(side_effect=[
        make_text_message("Hey babe."),
        make_text_message("NO_TOOL_CALLS"),
    ])
    seen = []
    agent.on_assistant_content = lambda t: seen.append(t)

    result = await agent.run("hi")
    assert result == "Hey babe."
    assert agent._complete.call_count == 2
    assert seen == ["Hey babe."]  # sentinel not surfaced
    # Challenge injected into history
    user_msgs = [m["content"] for m in agent._history if m.get("role") == "user"]
    assert any("NO_TOOL_CALLS" in (c or "") for c in user_msgs[1:])


async def test_require_no_tools_ack_allows_real_tool_after_prose():
    """Fake tool prose → challenge → real tool call → stop tools → final-output pass."""
    called = {}

    @tool
    def spy_tool(city: str) -> str:
        """Spy."""
        called["city"] = city
        return "sunny"

    agent = Agent(
        name="T",
        model=Model(id="grok-4.3", api_key="test-key"),
        tools=[spy_tool],
        require_no_tools_ack=True,
        max_turns=10,
    )
    agent._complete = AsyncMock(side_effect=[
        make_text_message("tool call spy_tool with city Austin — here you go"),
        make_tool_call_message("spy_tool", {"city": "Austin", "reason": "r"}),
        make_text_message(""),
        make_text_message("It's sunny."),
    ])
    result = await agent.run("pic?")
    assert called["city"] == "Austin"
    assert result == "It's sunny."
    # After tools: stop turn + forced final-output pass (no NO_TOOL_CALLS round-trip).
    assert agent._complete.call_count == 4


async def test_require_no_tools_ack_skipped_without_tools():
    """Gate is a no-op when the agent has no tools registered."""
    agent = Agent(
        name="T",
        model=Model(id="grok-4.3", api_key="test-key"),
        require_no_tools_ack=True,
    )
    agent._complete = AsyncMock(return_value=make_text_message("Hello!"))
    result = await agent.run("Say hi")
    assert result == "Hello!"
    assert agent._complete.call_count == 1


async def test_require_no_tools_ack_forced_after_max_challenges():
    """Three failed no-tool turns → force exit (no endless challenges)."""
    agent = Agent(
        name="T",
        model=Model(id="grok-4.3", api_key="test-key"),
        tools=[get_weather],
        require_no_tools_ack=True,
        no_tools_ack_max=3,
        max_turns=10,
    )
    agent._complete = AsyncMock(side_effect=[
        make_text_message("one"),    # fail 1 → challenge
        make_text_message("two"),    # fail 2 → challenge
        make_text_message("three"),  # fail 3 → force exit
    ])
    result = await agent.run("hi")
    assert result == "three"
    assert agent._complete.call_count == 3


async def test_tool_turn_freeform_content_not_emitted():
    """Free-form message.content on a tool-call turn is not user-facing."""
    @tool
    def send_pic(prompt: str) -> str:
        """Send a pic."""
        return "Image generated: https://example.com/x.png"

    agent = Agent(
        name="T",
        model=Model(id="grok-4.3", api_key="test-key"),
        tools=[send_pic],
        require_no_tools_ack=True,
        max_turns=10,
    )
    long_caption = (
        "Sure thing, babe. I've been thinking about you tonight anyway, "
        "so here's something just for you.\nHope you like it."
    )
    agent._complete = AsyncMock(side_effect=[
        make_tool_call_message(
            "send_pic", {"prompt": "selfie"}, content=long_caption,
        ),
        make_text_message(""),
        make_text_message("Hope you like it."),
    ])
    seen = []
    agent.on_assistant_content = lambda t: seen.append(t)

    result = await agent.run("pic?")
    assert long_caption not in seen
    assert seen == ["Hope you like it."]
    assert result == "Hope you like it."
    assert agent._complete.call_count == 3


async def test_update_for_user_emitted_as_tools_run():
    """Optional update_for_user on tool args is delivered when the tool starts."""
    @tool
    def send_pic(prompt: str) -> str:
        """Send a pic."""
        return "ok"

    agent = Agent(
        name="T",
        model=Model(id="grok-4.3", api_key="test-key"),
        tools=[send_pic],
        max_turns=10,
    )
    agent._complete = AsyncMock(side_effect=[
        make_tool_call_message(
            "send_pic",
            {"prompt": "x", "reason": "r", "update_for_user": "Sending a pic now."},
        ),
        make_text_message(""),
        make_text_message("Here you go."),
    ])
    seen = []
    agent.on_assistant_content = lambda t: seen.append(t)

    result = await agent.run("pic?")
    assert seen == ["Sending a pic now.", "Here you go."]
    assert result == "Here you go."


async def test_final_output_pass_after_tools():
    """After tools stop, inject a final-output prompt and take one more turn."""
    @tool
    def send_pic(prompt: str) -> str:
        """Send a pic."""
        return "ok"

    agent = Agent(
        name="T",
        model=Model(id="grok-4.3", api_key="test-key"),
        tools=[send_pic],
        require_no_tools_ack=True,
        max_turns=10,
    )
    agent._complete = AsyncMock(side_effect=[
        make_tool_call_message("send_pic", {"prompt": "x"}, content="Sent."),
        make_text_message("ignored intermediate"),
        make_text_message("Done."),
    ])
    seen = []
    agent.on_assistant_content = lambda t: seen.append(t)
    result = await agent.run("pic?")
    assert result == "Done."
    assert seen == ["Done."]
    assert agent._complete.call_count == 3
    user_msgs = [m["content"] for m in agent._history if m.get("role") == "user"]
    assert any("final output" in (c or "").lower() for c in user_msgs)


async def test_tools_used_skips_no_tools_ack_gate():
    """Once tools ran this run, no NO_TOOL_CALLS ack — final-output pass instead."""
    @tool
    def send_pic(prompt: str) -> str:
        """Send a pic."""
        return "ok"

    agent = Agent(
        name="T",
        model=Model(id="grok-4.3", api_key="test-key"),
        tools=[send_pic],
        require_no_tools_ack=True,
        max_turns=10,
    )
    agent._complete = AsyncMock(side_effect=[
        make_tool_call_message("send_pic", {"prompt": "x"}, content="Sent."),
        make_text_message(""),
        make_text_message("Done."),
    ])
    result = await agent.run("pic?")
    assert result == "Done."
    assert agent._complete.call_count == 3


async def test_force_tool_rejects_no_tools_ack():
    """While force_tool is active, NO_TOOL_CALLS is not an exit."""
    @tool
    def generate_image_krea(prompt: str) -> str:
        """Send a pic."""
        return "ok"

    agent = Agent(
        name="T",
        model=Model(id="grok-4.3", api_key="test-key"),
        tools=[generate_image_krea],
        require_no_tools_ack=True,
        force_tool="generate_image_krea",
        no_tools_ack_max=3,
        max_turns=10,
    )
    agent._complete = AsyncMock(side_effect=[
        make_text_message("here you go"),
        make_text_message("NO_TOOL_CALLS"),
        make_tool_call_message(
            "generate_image_krea",
            {"prompt": "a selfie", "reason": "r"},
        ),
        make_text_message(""),
        make_text_message("Pic sent."),
    ])
    result = await agent.run("send a pic")
    assert agent._tools_used_this_run is True
    assert agent._complete.call_count == 5
    assert result == "Pic sent."


async def test_custom_no_tools_ack_message_injected():
    agent = Agent(
        name="T",
        model=Model(id="grok-4.3", api_key="test-key"),
        tools=[get_weather],
        require_no_tools_ack=True,
        no_tools_ack_message="[System] SHOW_AND_TELL please",
        max_turns=10,
    )
    agent._complete = AsyncMock(side_effect=[
        make_text_message("hey"),
        make_text_message("NO_TOOL_CALLS"),
    ])
    await agent.run("hi")
    user_msgs = [m["content"] for m in agent._history if m.get("role") == "user"]
    assert any("SHOW_AND_TELL" in (c or "") for c in user_msgs)
