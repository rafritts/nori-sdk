import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nori import Agent, ContextFile, ContextRole


def make_agent(**kwargs):
    defaults = dict(name="Test", model="grok-4.3", system_prompt="You are helpful.")
    return Agent(**{**defaults, **kwargs})


def mock_completion(content: str = "Hello!"):
    message = MagicMock()
    message.content = content
    message.tool_calls = None
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.fixture
def patched_client(monkeypatch):
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        client = MagicMock()
        client.chat = MagicMock()
        client.chat.completions = MagicMock()
        client.chat.completions.create = AsyncMock(return_value=mock_completion())
        MockOpenAI.return_value = client
        yield client


async def test_system_prompt_maps_to_system_role(patched_client):
    agent = make_agent(system_prompt="Be concise.")
    await agent._complete([{"role": "user", "content": "Hi"}])
    messages = patched_client.chat.completions.create.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "Be concise."


async def test_context_role_system_appended_to_system_message(patched_client, tmp_path):
    f = tmp_path / "extra.md"
    f.write_text("Extra context.")
    agent = make_agent(
        system_prompt="Base prompt.",
        context_files=[ContextFile(path=f, role=ContextRole.SYSTEM)],
    )
    await agent._complete([{"role": "user", "content": "Hi"}])
    messages = patched_client.chat.completions.create.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert "Base prompt." in messages[0]["content"]
    assert "Extra context." in messages[0]["content"]


async def test_context_role_user_prepended_to_history(patched_client, tmp_path):
    f = tmp_path / "user_ctx.md"
    f.write_text("User context file.")
    agent = make_agent(
        context_files=[ContextFile(path=f, role=ContextRole.USER)],
    )
    history = [{"role": "user", "content": "Actual prompt"}]
    await agent._complete(history)
    messages = patched_client.chat.completions.create.call_args.kwargs["messages"]
    roles = [m["role"] for m in messages]
    user_indices = [i for i, r in enumerate(roles) if r == "user"]
    # context file user message must come before the history user message
    ctx_idx = next(i for i in user_indices if messages[i]["content"] == "User context file.")
    hist_idx = next(i for i in user_indices if messages[i]["content"] == "Actual prompt")
    assert ctx_idx < hist_idx


async def test_context_role_assistant_prepended_to_history(patched_client, tmp_path):
    f = tmp_path / "assistant_ctx.md"
    f.write_text("Assistant context.")
    agent = make_agent(
        context_files=[ContextFile(path=f, role=ContextRole.ASSISTANT)],
    )
    history = [{"role": "user", "content": "Hi"}]
    await agent._complete(history)
    messages = patched_client.chat.completions.create.call_args.kwargs["messages"]
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]
    assert any("Assistant context." in m["content"] for m in assistant_msgs)


async def test_returns_response_message(patched_client):
    agent = make_agent()
    msg = await agent._complete([{"role": "user", "content": "Hi"}])
    assert msg.content == "Hello!"


async def test_history_appended_after_context_files(patched_client, tmp_path):
    f = tmp_path / "user_ctx.md"
    f.write_text("Preamble.")
    agent = make_agent(context_files=[ContextFile(path=f, role=ContextRole.USER)])
    history = [{"role": "user", "content": "Real question"}]
    await agent._complete(history)
    messages = patched_client.chat.completions.create.call_args.kwargs["messages"]
    assert messages[-1]["content"] == "Real question"
