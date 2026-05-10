"""Unit tests for Scratchpad, Propagation, and ScratchpadUsage."""

import asyncio
import json
import os
from pydantic import BaseModel

from nori.enums import Propagation, ScratchpadUsage
from nori.scratchpad import Scratchpad, _scratchpad_var, _make_owner_tools, _make_propagate_tool


# ── Scratchpad: untyped ───────────────────────────────────────────────────────

def test_untyped_write_and_read():
    pad = Scratchpad()
    pad.write("key1", "hello")
    assert pad.read("key1") == "hello"

def test_untyped_read_missing_key():
    pad = Scratchpad()
    result = pad.read("missing")
    assert "not found" in result

def test_untyped_overwrite():
    pad = Scratchpad()
    pad.write("k", "first")
    pad.write("k", "second")
    assert pad.read("k") == "second"

def test_untyped_schema_prompt_empty():
    pad = Scratchpad()
    assert "empty" in pad.schema_prompt()

def test_untyped_schema_prompt_with_data():
    pad = Scratchpad()
    pad.write("findings", "slow queries")
    prompt = pad.schema_prompt()
    assert "slow queries" in prompt


# ── Scratchpad: typed (Pydantic schema) ───────────────────────────────────────

class Report(BaseModel):
    log_timeline: str = ""
    db_findings: str = ""
    approved: bool = False

def test_typed_write_valid_field():
    pad = Scratchpad(schema=Report)
    result = pad.write("log_timeline", "first 503 at 16:35")
    assert "Written" in result
    assert pad.read("log_timeline") == "first 503 at 16:35"

def test_typed_write_invalid_field():
    pad = Scratchpad(schema=Report)
    result = pad.write("nonexistent", "value")
    assert "not found" in result

def test_typed_read_valid_field():
    pad = Scratchpad(schema=Report)
    pad.write("db_findings", "missing index")
    assert pad.read("db_findings") == "missing index"

def test_typed_read_invalid_field():
    pad = Scratchpad(schema=Report)
    result = pad.read("nonexistent")
    assert "not found" in result
    assert "log_timeline" in result  # lists available fields

def test_typed_schema_prompt_contains_fields():
    pad = Scratchpad(schema=Report)
    prompt = pad.schema_prompt()
    assert "log_timeline" in prompt
    assert "db_findings" in prompt

def test_typed_is_typed():
    assert Scratchpad(schema=Report).is_typed is True
    assert Scratchpad().is_typed is False


# ── Propagation defaults ──────────────────────────────────────────────────────

def test_propagation_none_defaults_to_always():
    pad = Scratchpad(propagate=None)
    assert pad.propagate == Propagation.ALWAYS

def test_propagation_always():
    pad = Scratchpad(propagate=Propagation.ALWAYS)
    assert pad.propagate == Propagation.ALWAYS

def test_propagation_never():
    pad = Scratchpad(propagate=Propagation.NEVER)
    assert pad.propagate == Propagation.NEVER


# ── Usage prompts ─────────────────────────────────────────────────────────────

def test_usage_none_defaults_to_required():
    pad = Scratchpad()
    assert pad.usage == ScratchpadUsage.REQUIRED
    assert "required" in pad.usage_prompt().lower()

def test_usage_required_prompt():
    pad = Scratchpad(usage=ScratchpadUsage.REQUIRED)
    prompt = pad.usage_prompt()
    assert "required" in prompt.lower()
    assert len(prompt) > 20

def test_usage_selective_prompt():
    pad = Scratchpad(usage=ScratchpadUsage.SELECTIVE)
    prompt = pad.usage_prompt()
    assert "critical" in prompt.lower()


# ── Owner tools (closure-based) ───────────────────────────────────────────────

def test_owner_tools_read_write():
    pad = Scratchpad()
    read_tool, write_tool = _make_owner_tools(pad)

    async def go():
        await write_tool(key="x", value="hello")
        return await read_tool(key="x")

    result = asyncio.run(go())
    assert result.result == "hello"

def test_owner_tools_bypass_contextvar():
    """Owner tools work even when ContextVar is None."""
    pad = Scratchpad()
    read_tool, write_tool = _make_owner_tools(pad)

    async def go():
        # ContextVar is None (not set)
        assert _scratchpad_var.get() is None
        await write_tool(key="y", value="works")
        return await read_tool(key="y")

    result = asyncio.run(go())
    assert result.result == "works"

def test_owner_tools_have_correct_schema_name():
    pad = Scratchpad()
    read_tool, write_tool = _make_owner_tools(pad)
    assert read_tool.schema["function"]["name"] == "ScratchpadRead"
    assert write_tool.schema["function"]["name"] == "ScratchpadWrite"


# ── ContextVar-based tools (sub-agents) ──────────────────────────────────────

def test_contextvar_tools_return_none_message_when_no_pad():
    from nori.tools.scratchpad import ScratchpadRead, ScratchpadWrite

    async def go():
        read_result = await ScratchpadRead(key="x")
        write_result = await ScratchpadWrite(key="x", value="v")
        return read_result, write_result

    r, w = asyncio.run(go())
    assert "No scratchpad" in r.result
    assert "No scratchpad" in w.result

def test_contextvar_tools_work_when_pad_set():
    from nori.tools.scratchpad import ScratchpadRead, ScratchpadWrite

    pad = Scratchpad()

    async def go():
        token = _scratchpad_var.set(pad)
        try:
            await ScratchpadWrite(key="finding", value="pool exhausted")
            return await ScratchpadRead(key="finding")
        finally:
            _scratchpad_var.reset(token)

    result = asyncio.run(go())
    assert result.result == "pool exhausted"


# ── ScratchpadPropagate ───────────────────────────────────────────────────────

def test_propagate_tool_sets_contextvar():
    pad = Scratchpad(propagate=Propagation.DISCRETIONARY)
    propagate_tool = _make_propagate_tool(pad)

    async def go():
        assert _scratchpad_var.get() is None
        await propagate_tool()
        return _scratchpad_var.get()

    result = asyncio.run(go())
    assert result is pad

def test_propagate_tool_schema_name():
    pad = Scratchpad(propagate=Propagation.DISCRETIONARY)
    propagate_tool = _make_propagate_tool(pad)
    assert propagate_tool.schema["function"]["name"] == "ScratchpadPropagate"


# ── Agent integration ─────────────────────────────────────────────────────────

def test_agent_auto_injects_read_write_tools():
    from nori import Agent, Model
    pad = Scratchpad(propagate=Propagation.ALWAYS)
    agent = Agent(name="TestAgent", model=Model(id="x", api_key="k"), scratchpad=pad)
    assert "ScratchpadRead" in agent._tools
    assert "ScratchpadWrite" in agent._tools
    assert "ScratchpadPropagate" not in agent._tools  # ALWAYS — no need for propagate tool

def test_agent_injects_propagate_when_discretionary():
    from nori import Agent, Model
    pad = Scratchpad(propagate=Propagation.DISCRETIONARY)
    agent = Agent(name="TestAgent", model=Model(id="x", api_key="k"), scratchpad=pad)
    assert "ScratchpadPropagate" in agent._tools

def test_agent_does_not_inject_propagate_when_never():
    from nori import Agent, Model
    pad = Scratchpad(propagate=Propagation.NEVER)
    agent = Agent(name="TestAgent", model=Model(id="x", api_key="k"), scratchpad=pad)
    assert "ScratchpadPropagate" not in agent._tools


# ── Scratchpad: audit output ──────────────────────────────────────────────────

def test_dump_audit_untyped(tmp_path):
    path = str(tmp_path / "audit.json")
    pad = Scratchpad(audit_path=path)
    pad.write("finding", "index missing")
    pad.dump_audit("TestAgent")
    with open(path) as f:
        data = json.load(f)
    assert data["agent"] == "TestAgent"
    assert data["scratchpad"]["finding"] == "index missing"


def test_dump_audit_typed(tmp_path):
    class Findings(BaseModel):
        summary: str = ""
        bugs: str = ""

    path = str(tmp_path / "audit.json")
    pad = Scratchpad(schema=Findings, audit_path=path)
    pad.write("summary", "two bugs found")
    pad.dump_audit("CoordinatorAgent")
    with open(path) as f:
        data = json.load(f)
    assert data["agent"] == "CoordinatorAgent"
    assert data["scratchpad"]["summary"] == "two bugs found"
    assert data["scratchpad"]["bugs"] == ""


def test_dump_audit_no_op_when_no_path():
    pad = Scratchpad()
    pad.write("key", "value")
    pad.dump_audit("TestAgent")  # should not raise


def test_dump_audit_creates_parent_dirs(tmp_path):
    path = str(tmp_path / "nested" / "dir" / "audit.json")
    pad = Scratchpad(audit_path=path)
    pad.write("x", "y")
    pad.dump_audit("A")
    assert os.path.exists(path)
