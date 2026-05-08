import pytest

from nori.tool import tool
from nori.tools._bound import BoundTool


@tool
async def file_search(path: str, pattern: str) -> str:
    """Search files."""
    return f"searched {path} for {pattern}"


@tool
async def multi_param(a: str, b: str, c: str = "default") -> str:
    """Multi-param tool."""
    return f"{a},{b},{c}"


def test_bind_returns_bound_tool_instance():
    bound = file_search.bind(path="/tmp")
    assert isinstance(bound, BoundTool)
    assert bound is not file_search


def test_locked_param_removed_from_schema():
    bound = file_search.bind(path="/tmp")
    props = bound.schema["function"]["parameters"]["properties"]
    assert "path" not in props


def test_locked_param_not_in_required():
    bound = file_search.bind(path="/tmp")
    required = bound.schema["function"]["parameters"]["required"]
    assert "path" not in required


def test_unbound_param_still_in_schema():
    bound = file_search.bind(path="/tmp")
    props = bound.schema["function"]["parameters"]["properties"]
    assert "pattern" in props


async def test_locked_param_value_used_at_call_time():
    bound = file_search.bind(path="/tmp")
    result = await bound(pattern="*.py", reason="r")
    assert "/tmp" in result


async def test_model_cannot_override_locked_param():
    bound = file_search.bind(path="/tmp")
    # Passing path at call time — locked value should win
    result = await bound(path="/other", pattern="*.py", reason="r")
    assert "/tmp" in result
    assert "/other" not in result


def test_summarize_output_preserved():
    @tool(summarize_output=False)
    async def raw(x: str) -> str:
        """Raw."""
        return x

    bound = raw.bind(x="fixed")
    assert bound.summarize_output is False
