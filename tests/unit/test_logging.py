import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nori import Agent
from nori.tool import tool


def make_text_message(content="Done."):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    return msg


def make_tool_call_message(name, args, call_id="c1"):
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tc]
    return msg


def test_nori_agent_logger_exists():
    import nori.agent as agent_module
    assert agent_module.logger.name == "nori.agent"


def test_nori_narration_logger_exists():
    import nori.agent as agent_module
    assert agent_module.narration_logger.name == "nori.narration"


async def test_tool_call_logged_at_debug(caplog):
    @tool
    def sample_tool(x: str) -> str:
        """Sample."""
        return "ok"

    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        usage = MagicMock()
        usage.prompt_tokens = 5
        usage.completion_tokens = 3
        mock_client.chat.completions.create = AsyncMock(side_effect=[
            MagicMock(choices=[MagicMock(message=make_tool_call_message(
                "sample_tool", {"x": "val", "reason": "r"}
            ))], usage=usage),
            MagicMock(choices=[MagicMock(message=make_text_message())], usage=usage),
        ])
        MockOpenAI.return_value = mock_client

        with caplog.at_level(logging.DEBUG, logger="nori.agent"):
            agent = Agent(name="T", model="grok-4.3", tools=[sample_tool])
            agent.summarize_tool_output = False
            await agent.run("go")

    assert any("tool_call" in r.message for r in caplog.records)
    assert any("tool_result" in r.message for r in caplog.records)


async def test_tool_result_stored_in_log(caplog):
    @tool
    def sample_tool(x: str) -> str:
        """Sample."""
        return "the result"

    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        usage = MagicMock()
        usage.prompt_tokens = 5
        usage.completion_tokens = 3
        mock_client.chat.completions.create = AsyncMock(side_effect=[
            MagicMock(choices=[MagicMock(message=make_tool_call_message(
                "sample_tool", {"x": "val", "reason": "r"}
            ))], usage=usage),
            MagicMock(choices=[MagicMock(message=make_text_message())], usage=usage),
        ])
        MockOpenAI.return_value = mock_client

        agent = Agent(name="T", model="grok-4.3", tools=[sample_tool])
        agent.summarize_tool_output = False
        await agent.run("go")

    assert agent.tool_calls[0]["result"] == "the result"


async def test_on_tool_result_callback_fires(caplog):
    @tool
    def sample_tool(x: str) -> str:
        """Sample."""
        return "callback result"

    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        usage = MagicMock()
        usage.prompt_tokens = 5
        usage.completion_tokens = 3
        mock_client.chat.completions.create = AsyncMock(side_effect=[
            MagicMock(choices=[MagicMock(message=make_tool_call_message(
                "sample_tool", {"x": "val", "reason": "r"}
            ))], usage=usage),
            MagicMock(choices=[MagicMock(message=make_text_message())], usage=usage),
        ])
        MockOpenAI.return_value = mock_client

        received = []
        agent = Agent(name="T", model="grok-4.3", tools=[sample_tool])
        agent.summarize_tool_output = False
        agent.on_tool_result = lambda name, result: received.append((name, result))
        await agent.run("go")

    assert received == [("sample_tool", "callback result")]


async def test_narration_logged_at_debug(caplog):
    @tool
    def narr_tool(x: str) -> str:
        """Narr."""
        return "ok"

    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        usage = MagicMock()
        usage.prompt_tokens = 5
        usage.completion_tokens = 3
        mock_client.chat.completions.create = AsyncMock(side_effect=[
            MagicMock(choices=[MagicMock(message=make_tool_call_message(
                "narr_tool", {"x": "v", "reason": "my reason"}
            ))], usage=usage),
            MagicMock(choices=[MagicMock(message=make_text_message())], usage=usage),
        ])
        MockOpenAI.return_value = mock_client

        with caplog.at_level(logging.DEBUG, logger="nori.narration"):
            agent = Agent(name="T", model="grok-4.3", tools=[narr_tool])
            agent.summarize_tool_output = False
            await agent.run("go")

    assert any("narr_tool" in r.message for r in caplog.records)


async def test_error_logged_on_tool_failure(caplog):
    @tool
    def broken_tool(x: str) -> str:
        """Broken."""
        raise RuntimeError("exploded")

    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        usage = MagicMock()
        usage.prompt_tokens = 5
        usage.completion_tokens = 3
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[MagicMock(message=make_tool_call_message(
                "broken_tool", {"x": "v", "reason": "r"}
            ))], usage=usage)
        )
        MockOpenAI.return_value = mock_client

        with caplog.at_level(logging.ERROR, logger="nori.agent"):
            agent = Agent(name="T", model="grok-4.3", tools=[broken_tool])
            agent.summarize_tool_output = False
            with pytest.raises(RuntimeError):
                await agent.run("go")

    assert any("tool_error" in r.message for r in caplog.records)
