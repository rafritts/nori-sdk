import json
import re
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from nori import Agent, Model
from nori.tool import tool


def make_tool_call_message(name, args, call_id="c1"):
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tc]
    return msg


def make_two_tool_call_message(name1, args1, name2, args2):
    def make_tc(name, args, call_id):
        tc = MagicMock()
        tc.id = call_id
        tc.function.name = name
        tc.function.arguments = json.dumps(args)
        return tc

    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [
        make_tc(name1, args1, "c1"),
        make_tc(name2, args2, "c2"),
    ]
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


@tool
def spy_tool2(host: str) -> str:
    """Spy2."""
    return "up"


def make_agent(**kwargs):
    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), tools=[spy_tool, spy_tool2], **kwargs)
    agent._complete = AsyncMock(side_effect=[
        make_tool_call_message("spy_tool", {"city": "NYC", "reason": "checking"}),
        make_text_message(),
    ])
    return agent


async def test_trace_id_generated_at_run():
    agent = make_agent()
    assert agent.trace_id is None
    await agent.run("go")
    assert agent.trace_id is not None
    uuid.UUID(agent.trace_id)  # raises if not valid UUID


async def test_span_id_is_8_char_hex():
    agent = make_agent()
    await agent.run("go")
    assert agent.span_id is not None
    assert len(agent.span_id) == 8
    assert re.fullmatch(r"[0-9a-f]{8}", agent.span_id)


async def test_call_id_is_first_4_chars_of_span_id():
    fired = []
    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), tools=[spy_tool, spy_tool2])
    agent.narration = True
    agent.narration_call_id = True
    agent.on_narration = lambda s: fired.append(s)
    agent._complete = AsyncMock(side_effect=[
        make_two_tool_call_message(
            "spy_tool", {"city": "NYC", "reason": "r1"},
            "spy_tool2", {"host": "prod", "reason": "r2"},
        ),
        make_text_message(),
    ])
    await agent.run("go")
    # call_id should be 4 hex chars embedded in narration lines
    call_id_pattern = re.compile(r"-([0-9a-f]{4})\[")
    found = [call_id_pattern.search(s) for s in fired if call_id_pattern.search(s)]
    assert found, "Expected call_id in parallel narration output"


async def test_trace_id_inherited_by_sub_agent():
    parent = Agent(name="Parent", model=Model(id="grok-4.3", api_key="test-key"))
    parent._complete = AsyncMock(return_value=make_text_message("done"))
    await parent.run("go")
    parent_trace = parent.trace_id

    sub = Agent(name="Child", model=Model(id="grok-4.3", api_key="test-key"))
    sub._complete = AsyncMock(return_value=make_text_message("done"))
    await sub.run("subtask", _trace_id=parent_trace, _parent_span_id=parent.span_id)

    assert sub.trace_id == parent_trace


async def test_parent_span_id_set_on_sub_agent():
    parent = Agent(name="Parent", model=Model(id="grok-4.3", api_key="test-key"))
    parent._complete = AsyncMock(return_value=make_text_message("done"))
    await parent.run("go")
    parent_span = parent.span_id

    sub = Agent(name="Child", model=Model(id="grok-4.3", api_key="test-key"))
    sub._complete = AsyncMock(return_value=make_text_message("done"))
    await sub.run("subtask", _trace_id=parent.trace_id, _parent_span_id=parent_span)

    assert sub.parent_span_id == parent_span


async def test_call_id_absent_on_single_tool_call():
    fired = []
    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), tools=[spy_tool])
    agent.narration = True
    agent.on_narration = lambda s: fired.append(s)
    agent._complete = AsyncMock(side_effect=[
        make_tool_call_message("spy_tool", {"city": "NYC", "reason": "r"}),
        make_text_message(),
    ])
    await agent.run("go")
    # No call_id in single-tool narration
    assert not any(re.search(r"-[0-9a-f]{4}\[", s) for s in fired)


async def test_call_id_present_on_parallel_tool_calls():
    fired = []
    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), tools=[spy_tool, spy_tool2])
    agent.narration = True
    agent.on_narration = lambda s: fired.append(s)
    agent._complete = AsyncMock(side_effect=[
        make_two_tool_call_message(
            "spy_tool", {"city": "NYC", "reason": "r1"},
            "spy_tool2", {"host": "prod", "reason": "r2"},
        ),
        make_text_message(),
    ])
    await agent.run("go")
    assert any(re.search(r"-[0-9a-f]{4}\[", s) for s in fired)


async def test_narration_trace_id_opt_in():
    fired = []
    agent = make_agent()
    agent.narration = True
    agent.narration_trace_id = True
    agent.on_narration = lambda s: fired.append(s)
    await agent.run("go")
    trace_id = agent.trace_id
    assert any(trace_id in s for s in fired)


async def test_narration_call_id_opt_out():
    fired = []
    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), tools=[spy_tool, spy_tool2])
    agent.narration = True
    agent.narration_call_id = False
    agent.on_narration = lambda s: fired.append(s)
    agent._complete = AsyncMock(side_effect=[
        make_two_tool_call_message(
            "spy_tool", {"city": "NYC", "reason": "r1"},
            "spy_tool2", {"host": "prod", "reason": "r2"},
        ),
        make_text_message(),
    ])
    await agent.run("go")
    # With call_id opted out, no call_id in narration even on parallel
    assert not any(re.search(r"-[0-9a-f]{4}\[", s) for s in fired)


async def test_on_tool_result_receives_call_id_and_trace_id():
    received = []
    agent = make_agent()
    agent.on_tool_result = lambda name, result, call_id, trace_id: received.append((call_id, trace_id))
    await agent.run("go")
    assert len(received) == 1
    call_id, trace_id = received[0]
    assert re.fullmatch(r"[0-9a-f]{4}", call_id)
    assert trace_id == agent.trace_id


async def test_audit_events_carry_full_b3_fields(tmp_path):
    from nori.audit import AuditLogger

    log_file = tmp_path / "test.audit.log"
    agent = make_agent()
    agent.auditor = AuditLogger(str(log_file))
    await agent.run("go")
    agent.auditor.close()

    lines = [json.loads(l) for l in log_file.read_text().splitlines() if l.strip()]
    for event in lines:
        assert "trace_id" in event
        assert "span_id" in event
        assert "parent_span_id" in event
        if event["event"] in ("tool_call", "tool_result", "tool_error"):
            assert "call_id" in event


async def test_tool_span_parent_is_agent_span_id(tmp_path):
    from nori.audit import AuditLogger

    log_file = tmp_path / "test2.audit.log"
    agent = make_agent()
    agent.auditor = AuditLogger(str(log_file))
    await agent.run("go")
    agent.auditor.close()

    lines = [json.loads(l) for l in log_file.read_text().splitlines() if l.strip()]
    agent_start = next(e for e in lines if e["event"] == "agent_start")
    tool_calls = [e for e in lines if e["event"] == "tool_call"]
    assert tool_calls
    for tc in tool_calls:
        assert tc["parent_span_id"] == agent_start["span_id"]
