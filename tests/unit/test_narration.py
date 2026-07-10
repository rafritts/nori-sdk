import json
from unittest.mock import AsyncMock, MagicMock


from nori import Agent, Model
from nori.tool import tool


def make_tool_call_message(name, args, call_id="c1", content=None):
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = [tc]
    return msg


def make_text_message(content="Done."):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    return msg


@tool
def spy_tool(city: str) -> str:
    """Spy."""
    return "sunny"


def make_agent(**kwargs):
    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), tools=[spy_tool], **kwargs)
    return agent


async def test_narration_false_does_not_fire():
    fired = []
    agent = make_agent()
    agent.on_narration = lambda s: fired.append(s)
    agent.narration = False
    agent._complete = AsyncMock(side_effect=[
        make_tool_call_message("spy_tool", {"city": "Austin", "reason": "checking"}),
        make_text_message(""),
        make_text_message(),
    ])
    await agent.run("go")
    assert fired == []


async def test_on_narration_fires_before_tool_execution():
    order = []

    @tool
    def ordered_tool(x: str) -> str:
        """Ordered."""
        order.append("tool")
        return "ok"

    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), tools=[ordered_tool])
    agent.narration = True
    agent.on_narration = lambda s: order.append("narration")
    agent._complete = AsyncMock(side_effect=[
        make_tool_call_message("ordered_tool", {"x": "a", "reason": "r"}),
        make_text_message(""),
        make_text_message(),
    ])
    await agent.run("go")
    assert order.index("narration") < order.index("tool")


async def test_update_for_user_delivered_before_tool_executes():
    order = []

    @tool
    def ordered_tool(x: str) -> str:
        """Ordered."""
        order.append("tool")
        return "ok"

    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), tools=[ordered_tool])
    agent.narration = True
    agent.on_narration = lambda s: order.append(("response", s))
    agent.on_assistant_content = lambda s: order.append(("update", s))
    agent._complete = AsyncMock(side_effect=[
        make_tool_call_message(
            "ordered_tool",
            {"x": "a", "reason": "r", "update_for_user": "Checking now."},
        ),
        make_text_message(""),
        make_text_message("Done."),
    ])
    await agent.run("go")

    update_idx = next(
        i for i, e in enumerate(order)
        if isinstance(e, tuple) and e[0] == "update" and "Checking now" in e[1]
    )
    tool_idx = order.index("tool")
    assert update_idx < tool_idx


async def test_default_format_includes_tool_name_and_reason():
    fired = []
    agent = make_agent()
    agent.narration = True
    agent.on_narration = lambda s: fired.append(s)
    agent._complete = AsyncMock(side_effect=[
        make_tool_call_message("spy_tool", {"city": "NYC", "reason": "need weather"}),
        make_text_message(""),
        make_text_message(),
    ])
    await agent.run("go")
    assert any("spy_tool" in s and "need weather" in s for s in fired)


async def test_narrator_prefix_prepended():
    fired = []
    agent = make_agent()
    agent.narration = True
    agent.narrator_prefix = ">> "
    agent.on_narration = lambda s: fired.append(s)
    agent._complete = AsyncMock(side_effect=[
        make_tool_call_message("spy_tool", {"city": "LA", "reason": "r"}),
        make_text_message(""),
        make_text_message(),
    ])
    await agent.run("go")
    assert any(s.startswith(">> ") for s in fired)


async def test_narration_from_update_for_user():
    """Default on_assistant_content routes update_for_user into narration."""
    fired = []
    agent = make_agent()
    agent.narration = True
    agent.on_narration = lambda s: fired.append(s)
    agent._complete = AsyncMock(side_effect=[
        make_tool_call_message(
            "spy_tool",
            {"city": "LA", "reason": "r", "update_for_user": "I'll check the weather."},
        ),
        make_text_message(""),
        make_text_message("Sunny."),
    ])
    await agent.run("go")
    assert any("I'll check the weather." in s for s in fired)


async def test_on_assistant_content_receives_update_and_final():
    """update_for_user during tools + final-output pass content."""
    prose = []
    narrated = []
    agent = make_agent()
    agent.narration = True
    agent.on_narration = lambda s: narrated.append(s)
    agent.on_assistant_content = lambda s: prose.append(s)
    agent._complete = AsyncMock(side_effect=[
        make_tool_call_message(
            "spy_tool",
            {"city": "LA", "reason": "r", "update_for_user": "I'll check the weather."},
            content="long freeform that must not stream",
        ),
        make_text_message(""),
        make_text_message("Sunny in LA."),
    ])
    result = await agent.run("go")
    assert prose == ["I'll check the weather.", "Sunny in LA."]
    # Overridden callback must not also dump prose into narration.
    assert not any("I'll check the weather." in s for s in narrated)
    assert not any("Sunny in LA." in s for s in narrated)
    assert result == "Sunny in LA."


async def test_on_assistant_content_fires_before_tool():
    order = []

    @tool
    def ordered_tool(x: str) -> str:
        """Ordered."""
        order.append("tool")
        return "ok"

    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), tools=[ordered_tool])
    agent.narration = True
    agent.on_assistant_content = lambda s: order.append(("prose", s))
    agent._complete = AsyncMock(side_effect=[
        make_tool_call_message(
            "ordered_tool",
            {"x": "a", "reason": "r", "update_for_user": "Acting now."},
        ),
        make_text_message(""),
        make_text_message("Done."),
    ])
    await agent.run("go")
    prose_idx = next(i for i, e in enumerate(order) if isinstance(e, tuple) and e[0] == "prose")
    assert prose_idx < order.index("tool")


async def test_custom_callback_receives_string():
    received = []
    agent = make_agent()
    agent.narration = True
    agent.on_narration = lambda s: received.append(s)
    agent._complete = AsyncMock(side_effect=[
        make_tool_call_message("spy_tool", {"city": "NY", "reason": "r"}),
        make_text_message(""),
        make_text_message(),
    ])
    await agent.run("go")
    assert all(isinstance(s, str) for s in received)
