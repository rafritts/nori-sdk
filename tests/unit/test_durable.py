"""Crash recovery for agent runs and HITL waits."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

import nori
from nori import Agent, Model, Scratchpad
from nori.config import reset
from nori.exceptions import RunTimeout
from nori.durable import close_journal, get_journal
from nori.tool import tool
from nori.tools.human_input import HumanInput


def make_text_message(content="Done."):
    from unittest.mock import MagicMock
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    return msg


def make_tool_call_message(name, args, call_id="call_1", content=None):
    from unittest.mock import MagicMock
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = [tc]
    return msg


def make_agent(name, tools=None, scratchpad=None):
    return Agent(
        name=name,
        model=Model(id="grok-4.3", api_key="test-key"),
        tools=tools,
        scratchpad=scratchpad,
        max_turns=8,
    )


@pytest.fixture
def autouse_reset():
    reset()
    yield
    reset()
    close_journal()


@pytest.mark.asyncio
async def test_kill_during_tool_reruns_that_tool(autouse_reset):
    """A kill after a tool has started, but before its result is committed, runs it again."""
    calls = {"n": 0}
    started = asyncio.Event()
    release = asyncio.Event()

    @tool
    async def block(x: str) -> str:
        """Block until released."""
        calls["n"] += 1
        started.set()
        await release.wait()
        return "ok"

    first = make_agent("T", tools=[block])
    first._complete = AsyncMock(return_value=make_tool_call_message(
        "block", {"x": "1"}, "c1",
    ))
    task = asyncio.create_task(first.run("go", run_id="kill-tool"))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls["n"] == 1

    close_journal()
    release.set()
    second = make_agent("T", tools=[block])
    second._complete = AsyncMock(side_effect=[
        make_text_message(""),
        make_text_message("Done."),
    ])
    result = await second.run(run_id="kill-tool")
    assert result == "Done."
    assert calls["n"] == 2
    assert second._complete.call_count == 2


@pytest.mark.asyncio
async def test_kill_after_tool_does_not_repeat_it(autouse_reset):
    """A tool whose result was committed is not run again. The in-flight model call is."""
    calls = {"n": 0}

    @tool
    def spy(x: str) -> str:
        """Spy."""
        calls["n"] += 1
        return "ok"

    first = make_agent("T", tools=[spy])

    async def complete(_history):
        if calls["n"] == 0:
            return make_tool_call_message("spy", {"x": "1"}, "c1")
        raise asyncio.CancelledError()

    first._complete = complete
    with pytest.raises(asyncio.CancelledError):
        await first.run("go", run_id="kill-model")
    assert calls["n"] == 1

    close_journal()
    second = make_agent("T", tools=[spy])
    second._complete = AsyncMock(side_effect=[
        make_text_message(""),
        make_text_message("Done."),
    ])
    result = await second.run(run_id="kill-model")
    assert result == "Done."
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_finished_run_returns_stored_result(autouse_reset):
    agent = make_agent("T")
    agent._complete = AsyncMock(return_value=make_text_message("Hello"))
    assert await agent.run("hi", run_id="done-1") == "Hello"

    close_journal()
    again = make_agent("T")
    again._complete = AsyncMock(side_effect=AssertionError("model should not be called"))
    assert await again.run(run_id="done-1") == "Hello"
    assert await again.run("ignored", run_id="done-1") == "Hello"


@pytest.mark.asyncio
async def test_tool_exception_is_terminal(autouse_reset):
    calls = {"n": 0}

    @tool
    def boom(x: str) -> str:
        """Boom."""
        calls["n"] += 1
        raise RuntimeError("nope")

    first = make_agent("T", tools=[boom])
    first._complete = AsyncMock(return_value=make_tool_call_message("boom", {"x": "1"}, "c1"))
    with pytest.raises(RuntimeError, match="nope"):
        await first.run("go", run_id="err-1")
    assert calls["n"] == 1

    second = make_agent("T", tools=[boom])
    second._complete = AsyncMock(side_effect=AssertionError("model should not be called"))
    with pytest.raises(RuntimeError, match="nope"):
        await second.run(run_id="err-1")
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_hitl_answer_survives_kill(autouse_reset):
    """A committed answer is replayed. The human is not asked again."""
    nori.configure(server=True)
    from nori import server as srv
    srv._pending.clear()

    first = make_agent("T", tools=[HumanInput])
    first._complete = AsyncMock(return_value=make_tool_call_message(
        "HumanInput", {"question": "Approve?"}, "call_h",
    ))
    with patch.object(srv, "ensure_started", new=AsyncMock()):
        task = asyncio.create_task(first.run("go", run_id="hitl-1"))
        for _ in range(50):
            if srv._pending:
                break
            await asyncio.sleep(0.01)
        assert srv._pending
        request_id = next(iter(srv._pending))
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert srv._pending == {}
    journal = get_journal()
    assert journal.get_hitl("hitl-1", "call_h")["request_id"] == request_id
    assert journal.save_hitl_response(request_id, "yes") == "saved"
    from nori.server import _pending_view
    # Answered questions are no longer pending, even with no live process.
    assert _pending_view() == []

    close_journal()
    second = make_agent("T", tools=[HumanInput])
    second._complete = AsyncMock(side_effect=[
        make_text_message(""),
        make_text_message("Approved."),
    ])
    with patch.object(srv, "ensure_started", new=AsyncMock()):
        result = await second.run(run_id="hitl-1")
    assert result == "Approved."
    assert srv._pending == {}


@pytest.mark.asyncio
async def test_hitl_pending_survives_and_keeps_request_id(autouse_reset):
    """With no answer yet, resume waits on the same request id."""
    nori.configure(server=True)
    from nori import server as srv
    srv._pending.clear()

    first = make_agent("T", tools=[HumanInput])
    first._complete = AsyncMock(return_value=make_tool_call_message(
        "HumanInput", {"question": "Ship it?"}, "call_h",
    ))
    with patch.object(srv, "ensure_started", new=AsyncMock()):
        task = asyncio.create_task(first.run("go", run_id="hitl-2"))
        for _ in range(50):
            if srv._pending:
                break
            await asyncio.sleep(0.01)
        request_id = next(iter(srv._pending))
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    from nori.server import _pending_view
    close_journal()
    pending = _pending_view()
    assert [row["id"] for row in pending] == [request_id]
    assert pending[0]["question"] == "Ship it?"

    second = make_agent("T", tools=[HumanInput])
    second._complete = AsyncMock(side_effect=[
        make_text_message(""),
        make_text_message("Shipped."),
    ])

    async def answer():
        for _ in range(50):
            info = srv._pending.get(request_id)
            if info is not None and not info["future"].done():
                info["future"].set_result("yes")
                return
            await asyncio.sleep(0.01)
        raise AssertionError("resume did not re-register the HITL request")

    with patch.object(srv, "ensure_started", new=AsyncMock()):
        waiter = asyncio.create_task(answer())
        result = await second.run(run_id="hitl-2")
        await waiter
    assert result == "Shipped."


@pytest.mark.asyncio
async def test_nested_agent_is_not_repeated_after_it_finishes(autouse_reset):
    """A child run started from a tool keeps its own journal id and is not redone."""
    entered = {"n": 0}
    child = make_agent("Child")
    child._complete = AsyncMock(return_value=make_text_message("from-child"))

    @tool
    async def run_child(task: str) -> str:
        """Run the child on task."""
        entered["n"] += 1
        return await child.run(task)

    parent = make_agent("Parent", tools=[run_child])

    async def parent_complete(_history):
        if entered["n"] == 0:
            return make_tool_call_message("run_child", {"task": "do it"}, "c_child")
        raise asyncio.CancelledError()

    parent._complete = parent_complete
    with pytest.raises(asyncio.CancelledError):
        await parent.run("go", run_id="parent-1")
    assert entered["n"] == 1
    assert child.run_id == "parent-1/c_child"

    close_journal()
    child2 = make_agent("Child")
    child2._complete = AsyncMock(side_effect=AssertionError("child model should not run again"))

    @tool
    async def run_child(task: str) -> str:
        """Run the child on task."""
        entered["n"] += 1
        return await child2.run(task)

    parent2 = make_agent("Parent", tools=[run_child])
    parent2._complete = AsyncMock(side_effect=[
        make_text_message(""),
        make_text_message("Done."),
    ])
    assert await parent2.run(run_id="parent-1") == "Done."
    assert entered["n"] == 1


@pytest.mark.asyncio
async def test_scratchpad_and_system_prompt_survive(autouse_reset):
    holder = {}
    pad = Scratchpad()

    @tool
    def retitle(x: str) -> str:
        """Retitle the agent. x is ignored."""
        holder["agent"].system_prompt = "NEW PROMPT"
        pad.write("k", "v")
        return "ok"

    first = make_agent("T", tools=[retitle], scratchpad=pad)
    holder["agent"] = first

    async def complete(_history):
        if first.system_prompt != "NEW PROMPT":
            return make_tool_call_message("retitle", {"x": "1"}, "c1")
        raise asyncio.CancelledError()

    first._complete = complete
    with pytest.raises(asyncio.CancelledError):
        await first.run("go", run_id="state-1")

    close_journal()
    pad2 = Scratchpad()
    second = make_agent("T", tools=[retitle], scratchpad=pad2)
    second._complete = AsyncMock(side_effect=[
        make_text_message(""),
        make_text_message("Done."),
    ])
    assert await second.run(run_id="state-1") == "Done."
    assert second.system_prompt == "NEW PROMPT"
    assert pad2.read("k") == "v"


@pytest.mark.asyncio
async def test_nested_timeout_leaves_the_parent_resumable(autouse_reset):
    calls = {"n": 0}

    async def child_complete(_history):
        calls["n"] += 1
        if calls["n"] == 1:
            await asyncio.sleep(5)
        return make_text_message("from-child")

    child = make_agent("Child")
    child.run_timeout = 0.05
    child._complete = child_complete

    @tool
    async def run_child(task: str) -> str:
        """Run the child on task."""
        return await child.run(task)

    parent = make_agent("Parent", tools=[run_child])
    parent._complete = AsyncMock(return_value=make_tool_call_message(
        "run_child", {"task": "do it"}, "c1",
    ))
    with pytest.raises(RunTimeout):
        await parent.run("go", run_id="parent-timeout")
    assert get_journal().get_run("parent-timeout")["status"] == "running"

    close_journal()
    child2 = make_agent("Child")
    child2.run_timeout = 0.05
    child2._complete = child_complete

    @tool
    async def run_child(task: str) -> str:
        """Run the child on task."""
        return await child2.run(task)

    parent2 = make_agent("Parent", tools=[run_child])
    parent2._complete = AsyncMock(side_effect=[
        make_text_message(""),
        make_text_message("Done."),
    ])
    assert await parent2.run(run_id="parent-timeout") == "Done."
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_expanded_tool_stays_expanded_on_resume(autouse_reset):
    @tool
    def hidden(x: str) -> str:
        """Hidden tool. x is the input."""
        return "secret"

    def agent():
        return Agent(
            name="T",
            model=Model(id="grok-4.3", api_key="test-key"),
            deferred_tools=[hidden],
            max_turns=8,
        )

    first = agent()

    async def complete(_history):
        if "hidden" not in first._tools:
            return make_tool_call_message("ExpandTool", {"tool_name": "hidden"}, "c_exp")
        raise asyncio.CancelledError()

    first._complete = complete
    with pytest.raises(asyncio.CancelledError):
        await first.run("go", run_id="expand-1")
    assert "hidden" in first._tools

    close_journal()
    second = agent()
    assert "hidden" not in second._tools
    second._complete = AsyncMock(side_effect=[
        make_text_message(""),
        make_text_message("Done."),
    ])
    assert await second.run(run_id="expand-1") == "Done."
    assert "hidden" in second._tools
    assert "hidden" not in second._deferred_tools


@pytest.mark.asyncio
async def test_list_runs_and_disabled(autouse_reset, tmp_path):
    agent = make_agent("T")
    agent._complete = AsyncMock(return_value=make_text_message("Hi"))
    await agent.run("hi", run_id="list-1")
    rows = nori.list_runs(status="done")
    assert any(row["id"] == "list-1" and row["prompt"] == "hi" for row in rows)

    reset()
    close_journal()
    nori.configure(durable=False)
    plain = make_agent("T")
    plain._complete = AsyncMock(return_value=make_text_message("Hi"))
    assert await plain.run("hi") == "Hi"
    assert plain.run_id is None
    with pytest.raises(ValueError, match="disabled"):
        await plain.run("hi", run_id="nope")

    reset()
    close_journal()
    nori.configure(durable=str(tmp_path / "runs.db"))
    custom = make_agent("T")
    custom._complete = AsyncMock(return_value=make_text_message("Hi"))
    await custom.run("hi", run_id="custom-1")
    assert (tmp_path / "runs.db").exists()
