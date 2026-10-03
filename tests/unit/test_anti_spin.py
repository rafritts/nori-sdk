from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nori import Agent, Checkpoint, CheckpointScrutiny, Model
from nori.anti_spin import checkpoint_state, evaluate_checkpoint
from nori.exceptions import AntiSpinTerminated


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


def _agent(**kwargs):
    defaults = dict(name="T", model=Model(id="grok-4.3", api_key="test-key"), checkpoint=Checkpoint(every=1))
    defaults.update(kwargs)
    return Agent(**defaults)


async def test_checkpoint_fires_every_n_turns():
    judge = AsyncMock(return_value=(0.1, 10))
    with (
        patch("nori.agent.AsyncOpenAI") as MockOpenAI,
        patch("nori.anti_spin._judge", judge),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=[
            make_completion("turn 1"),
            make_completion("turn 2"),
        ])
        MockOpenAI.return_value = mock_client

        agent = _agent(max_turns=10)
        await agent.run("go")
        await agent.run("go again")
        assert mock_client.chat.completions.create.call_count == 2
        assert judge.call_count == 2


async def test_antispinterminated_raised_on_spin():
    judge = AsyncMock(return_value=(0.95, 10))
    with (
        patch("nori.agent.AsyncOpenAI") as MockOpenAI,
        patch("nori.anti_spin._judge", judge),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=make_completion("some output"))
        MockOpenAI.return_value = mock_client

        agent = _agent()
        with pytest.raises(AntiSpinTerminated, match=r"P\(spin\)=0.95"):
            await agent.run("go")
        assert mock_client.chat.completions.create.call_count == 1


async def test_no_exception_on_progress():
    judge = AsyncMock(return_value=(0.1, 10))
    with (
        patch("nori.agent.AsyncOpenAI") as MockOpenAI,
        patch("nori.anti_spin._judge", judge),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=make_completion("good output"))
        MockOpenAI.return_value = mock_client

        agent = _agent()
        result = await agent.run("go")
        assert result == "good output"


async def test_scrutiny_is_the_probability_cutoff():
    turns = [{"role": "assistant", "content": "trying again"}]
    with patch("nori.anti_spin._judge", AsyncMock(return_value=(0.60, 1))):
        strict = await evaluate_checkpoint(turns, CheckpointScrutiny.STRICT, task="finish the job")
        moderate = await evaluate_checkpoint(turns, CheckpointScrutiny.MODERATE, task="finish the job")
        lenient = await evaluate_checkpoint(turns, CheckpointScrutiny.LENIENT, task="finish the job")
    assert strict.spinning
    assert not moderate.spinning
    assert not lenient.spinning
    assert strict.threshold == 0.50
    assert moderate.threshold == 0.75
    assert lenient.threshold == 0.90


async def test_moderate_stops_at_the_boundary():
    turns = [{"role": "user", "content": "go"}]
    with patch("nori.anti_spin._judge", AsyncMock(return_value=(0.75, 1))):
        verdict = await evaluate_checkpoint(turns, CheckpointScrutiny.MODERATE)
    assert verdict.spinning


async def test_checkpoint_compact_records_the_verdict():
    judge = AsyncMock(return_value=(0.2, 10))
    with (
        patch("nori.agent.AsyncOpenAI") as MockOpenAI,
        patch("nori.anti_spin._judge", judge),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=make_completion("output"))
        MockOpenAI.return_value = mock_client

        agent = _agent(checkpoint=Checkpoint(every=1, compact=True))
        await agent.run("go")
        summary_msgs = [m for m in agent._history if m.get("_marker") == "__running_summary__"]
        assert len(summary_msgs) == 1
        assert "P(spin)=0.20" in summary_msgs[0]["content"]
        assert mock_client.chat.completions.create.call_count == 1


async def test_checkpoint_cost_is_added_and_reset():
    # 1_000_000 input tokens at $0.042 / million.
    judge = AsyncMock(return_value=(0.1, 1_000_000))
    with (
        patch("nori.agent.AsyncOpenAI") as MockOpenAI,
        patch("nori.anti_spin._judge", judge),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=make_completion("output"))
        MockOpenAI.return_value = mock_client

        agent = _agent()
        await agent.run("go")
        # grok-4.3: $1.25 / M input, $2.50 / M output. Usage is 5 prompt + 3 completion.
        chat = (5 * 1.25 + 3 * 2.50) / 1_000_000
        assert agent.cost == pytest.approx(chat + 0.042)
        agent.reset()
        assert agent.cost == 0.0


async def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="TYPESAFE_API_KEY"):
        await evaluate_checkpoint(
            [{"role": "user", "content": "go"}],
            CheckpointScrutiny.MODERATE,
        )


def test_state_names_tools_and_drops_images():
    payload = "A" * 500
    state = checkpoint_state(
        [
            {"role": "user", "content": "fix the bug"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "Bash", "arguments": '{"cmd": "ls"}'},
                }],
            },
            {
                "role": "tool",
                "tool_call_id": "call-1",
                "content": [
                    {"type": "text", "text": "file.py"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{payload}"}},
                ],
            },
            {"role": "user", "content": "old checkpoint note", "_marker": "__running_summary__"},
        ],
        task="fix the bug",
    )
    assert state["task"] == "fix the bug"
    assert state["recent_turns"][1]["tool_calls"] == [{"name": "Bash", "arguments": '{"cmd": "ls"}'}]
    tool_turn = state["recent_turns"][2]
    assert tool_turn["name"] == "Bash"
    assert "file.py" in tool_turn["content"]
    assert "[image]" in tool_turn["content"]
    assert payload not in tool_turn["content"]
    assert all("old checkpoint" not in t.get("content", "") for t in state["recent_turns"])


def test_state_clips_long_tool_output():
    state = checkpoint_state(
        [{"role": "tool", "tool_call_id": "x", "content": "z" * 5000}],
        task="",
    )
    content = state["recent_turns"][0]["content"]
    assert len(content) == 1501
    assert content.endswith("…")
    assert state["task"] == "(not recorded)"


async def test_empty_window_does_not_call_jev():
    judge = AsyncMock(return_value=(0.99, 10))
    with patch("nori.anti_spin._judge", judge):
        verdict = await evaluate_checkpoint(
            [{"role": "user", "content": "note", "_marker": "__running_summary__"}],
            CheckpointScrutiny.STRICT,
        )
    assert not verdict.spinning
    judge.assert_not_called()
