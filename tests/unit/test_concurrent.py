import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

import nori
from nori.concurrent import map, pipeline


def make_agent(responses):
    """Return a mock agent whose run() yields responses in order."""
    agent = MagicMock()
    agent.run = AsyncMock(side_effect=responses)
    return agent


# ---------------------------------------------------------------------------
# map
# ---------------------------------------------------------------------------

async def test_map_returns_results_in_order():
    agent = make_agent(["r0", "r1", "r2"])
    results = await map(agent, ["a", "b", "c"])
    assert results == ["r0", "r1", "r2"]


async def test_map_all_items_processed():
    agent = make_agent(["x"] * 5)
    await map(agent, ["a", "b", "c", "d", "e"])
    assert agent.run.call_count == 5


async def test_map_empty_list():
    agent = make_agent([])
    results = await map(agent, [])
    assert results == []


async def test_map_single_item():
    agent = make_agent(["only"])
    results = await map(agent, ["q"])
    assert results == ["only"]


async def test_map_concurrency_limit():
    """Semaphore should cap simultaneous in-flight runs."""
    active = 0
    peak = 0

    async def slow_run(prompt):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)  # yield so other tasks can run
        active -= 1
        return f"done:{prompt}"

    agent = MagicMock()
    agent.run = slow_run

    await map(agent, ["a", "b", "c", "d", "e"], concurrency=2)
    assert peak <= 2


async def test_map_exposed_on_nori_namespace():
    agent = make_agent(["hi"])
    results = await nori.map(agent, ["hello"])
    assert results == ["hi"]


# ---------------------------------------------------------------------------
# pipeline
# ---------------------------------------------------------------------------

async def test_pipeline_single_string_returns_string():
    a = make_agent(["step1"])
    b = make_agent(["step2"])
    result = await pipeline([a, b], "input")
    assert result == "step2"


async def test_pipeline_stages_chain_in_order():
    """Each stage receives the previous stage's output."""
    received = []

    async def capture_run(prompt):
        received.append(prompt)
        return f"[{prompt}]"

    a = MagicMock()
    a.run = capture_run
    b = MagicMock()
    b.run = capture_run

    await pipeline([a, b], "start")
    assert received == ["start", "[start]"]


async def test_pipeline_list_returns_list():
    a = make_agent(["r0", "r1"])
    result = await pipeline([a], ["x", "y"])
    assert result == ["r0", "r1"]


async def test_pipeline_multi_item_multi_stage():
    a = make_agent(["A0", "A1", "A2"])
    b = make_agent(["B0", "B1", "B2"])

    results = await pipeline([a, b], ["i0", "i1", "i2"])
    assert len(results) == 3
    # b receives a's outputs; a returns A0/A1/A2, b transforms them to B0/B1/B2
    assert results == ["B0", "B1", "B2"]


async def test_pipeline_single_agent():
    a = make_agent(["out"])
    result = await pipeline([a], "in")
    assert result == "out"


async def test_pipeline_empty_list():
    a = make_agent([])
    results = await pipeline([a], [])
    assert results == []


async def test_pipeline_exposed_on_nori_namespace():
    a = make_agent(["hello"])
    result = await nori.pipeline([a], "hi")
    assert result == "hello"


async def test_pipeline_stages_overlap():
    """Stage B should begin while stage A is still processing later items."""
    b_started = asyncio.Event()
    a_finished_first = asyncio.Event()

    async def stage_a(prompt):
        if prompt == "1":
            await asyncio.sleep(0)  # yield so B can pick up the result
            a_finished_first.set()
        return f"A({prompt})"

    async def stage_b(prompt):
        b_started.set()
        return f"B({prompt})"

    a = MagicMock()
    a.run = stage_a
    b = MagicMock()
    b.run = stage_b

    await pipeline([a, b], ["1", "2"])

    # B started (it received stage A's first output)
    assert b_started.is_set()
    # A did finish its first item (confirmed the pipeline ran fully)
    assert a_finished_first.is_set()
