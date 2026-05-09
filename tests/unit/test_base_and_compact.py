import asyncio

from nori.tools.base import BaseTool
from nori.tools.compact import Compact, COMPACT_TOOL_NAME
from nori.tool import tool


@tool
def sample(x: str, y: str) -> str:
    """Sample tool."""
    return f"{x}-{y}"


class SampleTool(BaseTool):
    schema = sample.schema
    summarize_output = True

    async def __call__(self, **kwargs):
        return await sample(**kwargs)


def test_base_bind_returns_bound_tool():
    from nori.tools._bound import BoundTool
    bound = SampleTool.bind(y="fixed")
    assert isinstance(bound, BoundTool)


def test_base_bind_removes_locked_param_from_schema():
    bound = SampleTool.bind(y="fixed")
    props = bound.schema["function"]["parameters"]["properties"]
    assert "y" not in props
    assert "x" in props


def test_compact_tool_name():
    assert Compact.schema["function"]["name"] == COMPACT_TOOL_NAME


def test_compact_summarize_output_false():
    assert Compact.summarize_output is False


def test_compact_is_coroutine():
    assert asyncio.iscoroutinefunction(Compact)
