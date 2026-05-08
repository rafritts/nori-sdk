import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nori import Agent
from nori.tool import tool


def make_text_message(content="Done."):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    return msg


def summary_response(text):
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def make_agent_with_mock(side_effects, **kwargs):
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=side_effects)
        MockOpenAI.return_value = mock_client
        agent = Agent(name="T", model="grok-3", **kwargs)
        return agent, mock_client


async def test_disabled_by_default():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[MagicMock(message=make_text_message())])
        )
        MockOpenAI.return_value = mock_client
        agent = Agent(name="T", model="grok-3")
        await agent.run("hi")
        assert not any(m.get("_marker") == "__running_summary__" for m in agent._history)


async def test_summary_injected_at_top_of_history():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        main_resp = MagicMock(choices=[MagicMock(message=make_text_message("answer"))])
        sum_resp = summary_response("Summary of work done.")
        mock_client.chat.completions.create = AsyncMock(side_effect=[main_resp, sum_resp])
        MockOpenAI.return_value = mock_client

        agent = Agent(name="T", model="grok-3")
        agent.running_context_summary = True
        await agent.run("do something")

        summary_msgs = [m for m in agent._history if m.get("_marker") == "__running_summary__"]
        assert len(summary_msgs) == 1
        assert "Summary of work done." in summary_msgs[0]["content"]


async def test_summary_role_is_user():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        main_resp = MagicMock(choices=[MagicMock(message=make_text_message())])
        sum_resp = summary_response("summary")
        mock_client.chat.completions.create = AsyncMock(side_effect=[main_resp, sum_resp])
        MockOpenAI.return_value = mock_client

        agent = Agent(name="T", model="grok-3")
        agent.running_context_summary = True
        await agent.run("go")

        summary_msgs = [m for m in agent._history if m.get("_marker") == "__running_summary__"]
        assert summary_msgs[0]["role"] == "user"


async def test_summary_updates_each_run():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=[
            MagicMock(choices=[MagicMock(message=make_text_message())]),
            summary_response("first summary"),
            MagicMock(choices=[MagicMock(message=make_text_message())]),
            summary_response("second summary"),
        ])
        MockOpenAI.return_value = mock_client

        agent = Agent(name="T", model="grok-3")
        agent.running_context_summary = True
        await agent.run("first")
        await agent.run("second")

        summary_msgs = [m for m in agent._history if m.get("_marker") == "__running_summary__"]
        assert len(summary_msgs) == 1
        assert "second summary" in summary_msgs[0]["content"]
