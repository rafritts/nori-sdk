import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nori import Agent, Checkpoint, CheckpointScrutiny, Model
from nori.anti_spin import evaluate_checkpoint
from nori.exceptions import AntiSpinTerminated
from nori.tool import tool


def make_text_message(content="Done."):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    return msg


def make_completion(content, prompt_tokens=5, completion_tokens=3):
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    return MagicMock(choices=[MagicMock(message=make_text_message(content))], usage=usage)


def spin_response():
    msg = MagicMock()
    msg.content = "The agent is repeating itself.\nSPIN"
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def progress_response():
    msg = MagicMock()
    msg.content = "The agent made good progress.\nPROGRESS"
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


async def test_checkpoint_fires_every_n_turns():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=[
            make_completion("turn 1"),
            progress_response(),
            make_completion("turn 2"),
            progress_response(),
        ])
        MockOpenAI.return_value = mock_client

        agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), max_turns=10, checkpoint=Checkpoint(every=1))
        await agent.run("go")
        await agent.run("go again")
        # evaluate_checkpoint called after each turn
        assert mock_client.chat.completions.create.call_count == 4


async def test_antispinterminated_raised_on_spin():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=[
            make_completion("some output"),
            spin_response(),
        ])
        MockOpenAI.return_value = mock_client

        agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), checkpoint=Checkpoint(every=1))
        with pytest.raises(AntiSpinTerminated):
            await agent.run("go")


async def test_no_exception_on_progress():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=[
            make_completion("good output"),
            progress_response(),
        ])
        MockOpenAI.return_value = mock_client

        agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), checkpoint=Checkpoint(every=1))
        result = await agent.run("go")
        assert result == "good output"


def test_strict_scrutiny_prompt_differs_from_lenient():
    assert (
        CheckpointScrutiny.STRICT != CheckpointScrutiny.LENIENT
    )
    from nori.anti_spin import _SCRUTINY_PROMPTS
    assert _SCRUTINY_PROMPTS[CheckpointScrutiny.STRICT] != _SCRUTINY_PROMPTS[CheckpointScrutiny.LENIENT]


async def test_checkpoint_compact_replaces_turns_on_pass():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=[
            make_completion("output"),
            progress_response(),
        ])
        MockOpenAI.return_value = mock_client

        agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), checkpoint=Checkpoint(every=1, compact=True))
        await agent.run("go")
        summary_msgs = [m for m in agent._history if m.get("_marker") == "__running_summary__"]
        assert len(summary_msgs) == 1
