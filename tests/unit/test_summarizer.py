import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nori import Agent, Model
from nori.tool import tool


def make_summarizer_response(text="summarized"):
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def make_tool_call_message(name, args, call_id="c1"):
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tc]
    return msg


def make_text_message(content="Done."):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    return msg


@tool
def big_output(x: str) -> str:
    """Returns large output."""
    return "a" * 5000


@tool(summarize_output=False)
def raw_tool(x: str) -> str:
    """Raw output tool."""
    return "raw_result"


async def test_reason_passed_as_hint():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        # First call: main completion returning a tool call
        # Second call: summarizer
        # Third call: final text response
        main_resp = MagicMock(choices=[MagicMock(message=make_tool_call_message(
            "big_output", {"x": "data", "reason": "find the key metric"}
        ))])
        summarizer_resp = make_summarizer_response("summary here")
        final_resp = MagicMock(choices=[MagicMock(message=make_text_message("All done."))])

        mock_client.chat.completions.create = AsyncMock(
            side_effect=[main_resp, summarizer_resp, final_resp]
        )
        MockOpenAI.return_value = mock_client

        agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), tools=[big_output], summarize_tool_output=True)
        await agent.run("go")

        # Second call is the summarizer
        summarizer_call = mock_client.chat.completions.create.call_args_list[1]
        prompt = summarizer_call.kwargs["messages"][0]["content"]
        assert "find the key metric" in prompt


async def test_summarized_content_appended():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        main_resp = MagicMock(choices=[MagicMock(message=make_tool_call_message(
            "big_output", {"x": "d", "reason": "r"}
        ))])
        summarizer_resp = make_summarizer_response("THE SUMMARY")
        final_resp = MagicMock(choices=[MagicMock(message=make_text_message("Done."))])
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[main_resp, summarizer_resp, final_resp]
        )
        MockOpenAI.return_value = mock_client

        agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), tools=[big_output], summarize_tool_output=True)
        await agent.run("go")

        tool_msg = next(m for m in agent._history if m.get("role") == "tool")
        assert tool_msg["content"] == "THE SUMMARY"


async def test_summarize_output_false_skips_summarizer():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        main_resp = MagicMock(choices=[MagicMock(message=make_tool_call_message(
            "raw_tool", {"x": "d", "reason": "r"}
        ))])
        final_resp = MagicMock(choices=[MagicMock(message=make_text_message("Done."))])
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[main_resp, final_resp]
        )
        MockOpenAI.return_value = mock_client

        agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), tools=[raw_tool])
        await agent.run("go")

        # Only 2 calls: main loop + final response (no summarizer call)
        assert mock_client.chat.completions.create.call_count == 2
        tool_msg = next(m for m in agent._history if m.get("role") == "tool")
        assert tool_msg["content"] == "raw_result"


async def test_agent_level_summarize_false_skips_all():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        main_resp = MagicMock(choices=[MagicMock(message=make_tool_call_message(
            "big_output", {"x": "d", "reason": "r"}
        ))])
        final_resp = MagicMock(choices=[MagicMock(message=make_text_message("Done."))])
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[main_resp, final_resp]
        )
        MockOpenAI.return_value = mock_client

        agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), tools=[big_output])
        await agent.run("go")

        assert mock_client.chat.completions.create.call_count == 2
