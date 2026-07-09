"""tool_args_filter / tool_schema_filter hooks on Agent."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nori import Agent
from nori.model import Model
from nori.providers import Provider


def _fake_model():
    return Model(id="test-model", provider=Provider.XAI, api_key="test")


def test_tool_schema_filter_strips_params():
    def schema_filter(name: str, schema: dict) -> dict:
        if name == "generate_image_krea":
            props = schema["function"]["parameters"]["properties"]
            props.pop("aspect_ratio", None)
            req = schema["function"]["parameters"].get("required", [])
            schema["function"]["parameters"]["required"] = [
                r for r in req if r != "aspect_ratio"
            ]
        return schema

    tool = SimpleNamespace(
        schema={
            "type": "function",
            "function": {
                "name": "generate_image_krea",
                "description": "img",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "aspect_ratio": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["prompt", "aspect_ratio", "reason"],
                },
            },
        },
        summarize_output=True,
    )

    agent = Agent(
        name="t",
        model=_fake_model(),
        tools=[tool],
        tool_schema_filter=schema_filter,
        max_turns=1,
    )
    schemas = agent._tool_schemas()
    assert len(schemas) == 1
    props = schemas[0]["function"]["parameters"]["properties"]
    assert "aspect_ratio" not in props
    assert "prompt" in props
    assert "aspect_ratio" not in schemas[0]["function"]["parameters"]["required"]
    # Original tool schema unchanged
    assert "aspect_ratio" in tool.schema["function"]["parameters"]["properties"]


def test_tool_args_filter_overrides_before_call():
    seen: list[dict] = []

    async def fake_tool(**kwargs):
        seen.append(kwargs)
        return "ok"

    fake_tool.schema = {
        "type": "function",
        "function": {
            "name": "generate_image_krea",
            "description": "img",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "aspect_ratio": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["prompt", "reason"],
            },
        },
    }
    fake_tool.summarize_output = False

    def args_filter(name: str, args: dict) -> dict:
        assert name == "generate_image_krea"
        out = dict(args)
        out["aspect_ratio"] = "1:1 (Square)"
        return out

    agent = Agent(
        name="t",
        model=_fake_model(),
        tools=[fake_tool],
        tool_args_filter=args_filter,
        max_turns=1,
    )
    agent.narration = False

    tc = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(
            name="generate_image_krea",
            arguments=json.dumps(
                {
                    "prompt": "a cat",
                    "aspect_ratio": "16:9 (Widescreen)",
                    "reason": "test",
                }
            ),
        ),
    )

    asyncio.run(agent._invoke_tool(tc))
    assert seen == [
        {
            "prompt": "a cat",
            "aspect_ratio": "1:1 (Square)",
            "reason": "test",
        }
    ]
