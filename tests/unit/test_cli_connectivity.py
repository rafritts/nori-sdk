"""Tests for SPEC-19: CLI agent connectivity providers."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai.types.chat import ChatCompletionMessage

from nori import Agent, Model, Provider
from nori.cli_backends import (
    ClaudeCliBackend,
    CodexCliBackend,
    GrokCliBackend,
    backend_for_provider,
)
from nori.completer import (
    CliCompleter,
    CompletionResult,
    OpenAICompleter,
    parse_cli_message,
    serialize_for_cli,
)


# ── Provider / Model ──────────────────────────────────────────────────────────

def test_cli_providers_require_no_api_key():
    for p in (Provider.GROK_CLI, Provider.CLAUDE_CLI, Provider.CODEX_CLI):
        m = Model(id="test-model", provider=p)
        assert m.api_key is None
        assert m.provider.is_cli
        assert m.provider.cli_binary in {"grok", "claude", "codex"}


def test_cli_provider_is_cli_flag():
    assert Provider.GROK_CLI.is_cli
    assert Provider.CLAUDE_CLI.is_cli
    assert Provider.CODEX_CLI.is_cli
    assert not Provider.XAI.is_cli
    assert not Provider.OPENAI.is_cli


def test_backend_for_provider():
    assert isinstance(backend_for_provider(Provider.GROK_CLI), GrokCliBackend)
    assert isinstance(backend_for_provider(Provider.CLAUDE_CLI), ClaudeCliBackend)
    assert isinstance(backend_for_provider(Provider.CODEX_CLI), CodexCliBackend)


def test_model_cli_path_field():
    m = Model(id="grok-4.5", provider=Provider.GROK_CLI, cli_path="/opt/grok")
    assert m.cli_path == "/opt/grok"


# ── Argv construction ─────────────────────────────────────────────────────────

def test_grok_argv_disables_tools_and_uses_json():
    backend = GrokCliBackend()
    argv = backend.build_argv(
        binary="/usr/bin/grok",
        model="grok-4.5",
        system="You are helpful.",
        prompt="hi",
        prompt_file="/tmp/prompt.txt",
    )
    assert argv[0] == "/usr/bin/grok"
    assert "--tools" in argv and argv[argv.index("--tools") + 1] == ""
    assert "--output-format" in argv and argv[argv.index("--output-format") + 1] == "json"
    assert "-m" in argv and argv[argv.index("-m") + 1] == "grok-4.5"
    assert "--prompt-file" in argv
    assert "--system-prompt-override" in argv


def test_claude_argv_disables_tools():
    backend = ClaudeCliBackend()
    argv = backend.build_argv(
        binary="/usr/bin/claude",
        model="claude-sonnet-4-6",
        system="sys",
        prompt="hello",
    )
    assert argv[0] == "/usr/bin/claude"
    assert "-p" in argv
    assert "--tools" in argv and argv[argv.index("--tools") + 1] == ""
    assert "--output-format" in argv and argv[argv.index("--output-format") + 1] == "json"
    assert "--model" in argv and argv[argv.index("--model") + 1] == "claude-sonnet-4-6"
    assert "--system-prompt" in argv


def test_codex_argv_uses_exec():
    backend = CodexCliBackend()
    argv = backend.build_argv(
        binary="codex",
        model="gpt-5.4",
        system=None,
        prompt="hi",
    )
    assert argv[:2] == ["codex", "exec"]
    assert "-m" in argv and argv[argv.index("-m") + 1] == "gpt-5.4"
    assert "--json" in argv
    assert argv[-1] == "-"


# ── Envelope parse / serialize ────────────────────────────────────────────────

def test_parse_content_only():
    msg = parse_cli_message('{"content":"hello"}')
    assert msg.content == "hello"
    assert not msg.tool_calls


def test_parse_tool_calls():
    raw = json.dumps({
        "tool_calls": [
            {"id": "c1", "name": "Bash", "arguments": {"command": "ls", "reason": "list"}},
        ]
    })
    msg = parse_cli_message(raw)
    assert msg.content is None or msg.content == ""
    assert msg.tool_calls is not None
    assert len(msg.tool_calls) == 1
    assert msg.tool_calls[0].function.name == "Bash"
    args = json.loads(msg.tool_calls[0].function.arguments)
    assert args["command"] == "ls"


def test_parse_multi_tool_calls():
    raw = json.dumps({
        "content": "working",
        "tool_calls": [
            {"name": "Bash", "arguments": {"command": "a", "reason": "r"}},
            {"name": "FileRead", "arguments": {"path": "x", "reason": "r"}},
        ],
    })
    msg = parse_cli_message(raw)
    assert msg.content == "working"
    assert len(msg.tool_calls) == 2


def test_parse_malformed_falls_back_to_content():
    msg = parse_cli_message("just plain prose")
    assert msg.content == "just plain prose"
    assert not msg.tool_calls


def test_parse_markdown_fenced_json():
    msg = parse_cli_message('```json\n{"content":"fenced"}\n```')
    assert msg.content == "fenced"


def test_claude_extract_text_result_field():
    backend = ClaudeCliBackend()
    stdout = json.dumps({
        "type": "result",
        "is_error": False,
        "result": '{"content":"pong"}',
    })
    text = backend.extract_text(stdout)
    assert "pong" in text or text == '{"content":"pong"}'


def test_claude_extract_raises_on_error():
    backend = ClaudeCliBackend()
    stdout = json.dumps({
        "type": "result",
        "is_error": True,
        "result": "Failed to authenticate",
    })
    with pytest.raises(RuntimeError, match="authenticate"):
        backend.extract_text(stdout)


def test_serialize_includes_tools_and_history():
    messages = [
        {"role": "system", "content": "Be concise."},
        {"role": "user", "content": "list files"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "c1",
                "type": "function",
                "function": {"name": "Bash", "arguments": '{"command":"ls"}'},
            }],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "a.txt"},
    ]
    tools = [{
        "type": "function",
        "function": {
            "name": "Bash",
            "description": "Run shell",
            "parameters": {"type": "object", "properties": {}},
        },
    }]
    system, body = serialize_for_cli(messages, tools=tools)
    assert system is not None
    assert "DO NOT USE YOUR OWN TOOLS" in system
    assert "Be concise." in system
    assert "list files" in body
    assert "Bash" in body
    assert "tool_calls" in body
    assert "Available tools" in body
    assert "DO NOT USE YOUR OWN (CLI-native) TOOLS" in body


def test_serialize_always_bans_cli_native_tools():
    system, body = serialize_for_cli([{"role": "user", "content": "hi"}])
    assert system is not None
    assert "DO NOT USE YOUR OWN TOOLS" in system
    assert "no built-in agent tools" in system.lower()
    assert "DO NOT USE YOUR OWN TOOLS" in body


def test_serialize_tool_choice_none():
    tools = [{"type": "function", "function": {"name": "Bash", "description": "", "parameters": {}}}]
    _, body = serialize_for_cli(
        [{"role": "user", "content": "done?"}],
        tools=tools,
        tool_choice="none",
    )
    assert "tool_choice=none" in body


# ── CliCompleter ──────────────────────────────────────────────────────────────

def test_cli_completer_missing_binary(monkeypatch):
    monkeypatch.setattr("nori.completer.shutil.which", lambda _: None)
    with pytest.raises(FileNotFoundError, match="grok"):
        CliCompleter(GrokCliBackend())


async def test_cli_completer_complete_parses_envelope(monkeypatch, tmp_path):
    monkeypatch.setattr("nori.completer.shutil.which", lambda _: "/usr/bin/grok")

    async def fake_run(argv, stdin_data=None, timeout=None):
        return json.dumps({"content": "hi from cli"}), "", 0

    monkeypatch.setattr("nori.completer._run_subprocess", fake_run)
    # Avoid real temp-file issues — still exercise file mode
    completer = CliCompleter(GrokCliBackend(), binary_path="/usr/bin/grok")
    result = await completer.complete(
        model="grok-4.5",
        messages=[{"role": "user", "content": "hello"}],
    )
    assert isinstance(result, CompletionResult)
    assert result.message.content == "hi from cli"


async def test_cli_completer_nonzero_exit(monkeypatch):
    monkeypatch.setattr("nori.completer.shutil.which", lambda _: "/usr/bin/claude")

    async def fake_run(argv, stdin_data=None, timeout=None):
        return "", "auth failed", 1

    monkeypatch.setattr("nori.completer._run_subprocess", fake_run)
    completer = CliCompleter(ClaudeCliBackend(), binary_path="/usr/bin/claude")
    with pytest.raises(RuntimeError, match="exited with code 1"):
        await completer.complete(
            model="claude-sonnet-4-6",
            messages=[{"role": "user", "content": "hi"}],
        )


# ── Agent loop with fake CliCompleter ─────────────────────────────────────────

async def test_agent_cli_loop_tool_then_final(monkeypatch):
    """Agent with GROK_CLI runs Nori tools via envelope tool_calls."""
    from nori.tool import tool

    @tool
    def echo_tool(text: str) -> str:
        """Echo text back."""
        return f"echo:{text}"

    calls = {"n": 0}

    class FakeCliCompleter:
        async def complete(self, *, model, messages, tools=None, tool_choice=None, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                msg = parse_cli_message(json.dumps({
                    "tool_calls": [{
                        "id": "c1",
                        "name": "echo_tool",
                        "arguments": {"text": "hi", "reason": "test"},
                    }],
                }))
                return CompletionResult(message=msg)
            # After tools, final output path may request tool_choice=none.
            return CompletionResult(
                message=ChatCompletionMessage(role="assistant", content="done with tools")
            )

    monkeypatch.setattr(
        "nori.agent.CliCompleter.from_model",
        classmethod(lambda cls, model, timeout=None: FakeCliCompleter()),
    )

    agent = Agent(
        name="cli-agent",
        model=Model(id="grok-4.5", provider=Provider.GROK_CLI),
        tools=[echo_tool],
        max_turns=5,
    )
    # Avoid hanging if more turns needed — FakeCli always returns content after first.
    result = await agent.run("use the tool")
    assert "done" in result.lower() or result
    assert calls["n"] >= 1
    # Tool should have run
    assert any(e.get("name") == "echo_tool" for e in agent._tool_calls_log)


async def test_agent_cli_does_not_build_openai_client():
    agent = Agent(
        name="cli-agent",
        model=Model(id="grok-4.5", provider=Provider.GROK_CLI),
    )
    with pytest.raises(RuntimeError, match="CLI backend"):
        _ = agent._client


async def test_openai_completer_still_works():
    client = MagicMock()
    msg = MagicMock()
    msg.content = "ok"
    msg.tool_calls = None
    usage = MagicMock(prompt_tokens=1, completion_tokens=1)
    client.chat.completions.create = AsyncMock(
        return_value=MagicMock(choices=[MagicMock(message=msg)], usage=usage)
    )
    completer = OpenAICompleter(client)
    result = await completer.complete(
        model="grok-4.5",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert result.message.content == "ok"
    assert result.usage is usage


async def test_agent_http_path_unchanged_with_patch():
    """Existing test pattern: patch AsyncOpenAI still drives the agent."""
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        msg = MagicMock()
        msg.content = "pong"
        msg.tool_calls = None
        usage = MagicMock()
        usage.prompt_tokens = 3
        usage.completion_tokens = 2
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[MagicMock(message=msg)], usage=usage)
        )
        MockOpenAI.return_value = mock_client

        agent = Agent(name="T", model=Model(id="grok-4.5", api_key="test-key"))
        result = await agent.run("ping")
        assert result == "pong"
        mock_client.chat.completions.create.assert_awaited()
