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


# ── Parse / serialize (text-only, no tools) ───────────────────────────────────

def test_parse_content_only():
    msg = parse_cli_message('{"content":"hello"}')
    assert msg.content == "hello"
    assert not msg.tool_calls


def test_parse_strips_tool_calls():
    raw = json.dumps({
        "tool_calls": [
            {"id": "c1", "name": "Bash", "arguments": {"command": "ls", "reason": "list"}},
        ]
    })
    msg = parse_cli_message(raw)
    assert not msg.tool_calls
    assert msg.content  # placeholder explaining tools are disabled


def test_parse_content_wins_over_tool_calls():
    raw = json.dumps({
        "content": "working",
        "tool_calls": [
            {"name": "Bash", "arguments": {"command": "a", "reason": "r"}},
        ],
    })
    msg = parse_cli_message(raw)
    assert msg.content == "working"
    assert not msg.tool_calls


def test_parse_malformed_falls_back_to_content():
    msg = parse_cli_message("just plain prose")
    assert msg.content == "just plain prose"
    assert not msg.tool_calls


def test_parse_markdown_fenced_json():
    msg = parse_cli_message('```json\n{"content":"fenced"}\n```')
    assert msg.content == "fenced"
    assert not msg.tool_calls


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


def test_serialize_history_without_tools():
    messages = [
        {"role": "system", "content": "Be concise."},
        {"role": "user", "content": "list files"},
        {
            "role": "assistant",
            "content": "I cannot list files.",
            "tool_calls": [{
                "id": "c1",
                "type": "function",
                "function": {"name": "Bash", "arguments": '{"command":"ls"}'},
            }],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "a.txt"},
    ]
    system, body = serialize_for_cli(messages)
    assert system is not None
    assert "TOOLS FORBIDDEN" in system or "YOU HAVE NO TOOLS" in system
    assert "TOOL CALLING IS COMPLETELY DISABLED" in system
    assert "Be concise." in system
    assert "list files" in body
    assert "Available tools" not in body
    assert "nori tools" not in body.lower()
    # Historical tool call payloads must not be re-serialized (ban text may mention the word)
    assert '"name": "Bash"' not in body
    assert "tool (id=" not in body
    assert "TOOLS ARE BANNED" in body


def test_serialize_aggressive_no_tools_ban():
    system, body = serialize_for_cli([{"role": "user", "content": "hi"}])
    assert system is not None
    assert "YOU HAVE NO TOOLS" in system
    assert "TOOL CALLING IS COMPLETELY DISABLED" in system
    assert "Nori tool envelope" in system or "no Nori tool envelope" in system.lower()
    assert "TOOLS ARE BANNED" in body
    assert "plain text" in body.lower()


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


# ── Agent: CLI path is tool-free ──────────────────────────────────────────────

def test_agent_cli_rejects_tools():
    from nori.tool import tool

    @tool
    def echo_tool(text: str) -> str:
        """Echo text back."""
        return f"echo:{text}"

    with pytest.raises(ValueError, match="tool calling is completely disabled"):
        Agent(
            name="cli-agent",
            model=Model(id="grok-4.5", provider=Provider.GROK_CLI),
            tools=[echo_tool],
        )


def test_agent_cli_rejects_deferred_and_mcp():
    from nori.tool import tool

    @tool
    def echo_tool(text: str) -> str:
        """Echo."""
        return text

    with pytest.raises(ValueError, match="deferred_tools"):
        Agent(
            name="cli-agent",
            model=Model(id="grok-4.5", provider=Provider.GROK_CLI),
            deferred_tools=[echo_tool],
        )


def test_agent_cli_registers_no_tools():
    agent = Agent(
        name="cli-agent",
        model=Model(id="grok-4.5", provider=Provider.GROK_CLI),
    )
    assert agent._tools == {}
    assert agent._deferred_tools == {}
    assert agent._mcp_servers == []


async def test_agent_cli_loop_text_only(monkeypatch):
    """Agent with GROK_CLI returns plain text; never runs tools."""
    calls = {"n": 0, "tools_arg": None}

    class FakeCliCompleter:
        async def complete(self, *, model, messages, tools=None, tool_choice=None, **kwargs):
            calls["n"] += 1
            calls["tools_arg"] = tools
            return CompletionResult(
                message=ChatCompletionMessage(role="assistant", content="plain answer")
            )

    monkeypatch.setattr(
        "nori.agent.CliCompleter.from_model",
        classmethod(lambda cls, model, timeout=None: FakeCliCompleter()),
    )

    agent = Agent(
        name="cli-agent",
        model=Model(id="grok-4.5", provider=Provider.GROK_CLI),
        max_turns=3,
    )
    result = await agent.run("hello")
    assert result == "plain answer"
    assert calls["n"] == 1
    assert calls["tools_arg"] is None
    assert agent._tool_calls_log == []


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
