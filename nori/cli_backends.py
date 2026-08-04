"""Per-vendor CLI backends used as model connectivity only.

These adapters turn a serialized Nori completion into a headless CLI invocation
with ALL tools disabled (vendor CLI tools off; Nori tools are not used on this
path either). See specs/SPEC-19-cli-agent-connectivity.md.
"""
from __future__ import annotations

import json
import logging
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger("nori.cli_backends")

PromptMode = Literal["arg", "stdin", "file"]


@dataclass(frozen=True)
class CliBackend:
    """How to invoke one vendor CLI for a single completion turn."""

    name: str
    binary: str
    prompt_mode: PromptMode
    install_hint: str

    def allocate_session_id(self) -> str | None:
        """Pre-allocate a session id when the CLI persists by default (e.g. Grok).

        Returned id is passed to ``build_argv`` and deleted via
        ``cleanup_session_argv`` after the run so one-shot completions do not
        pile up in the user's session history.
        """
        return None

    def build_argv(
        self,
        *,
        binary: str,
        model: str,
        system: str | None,
        prompt: str,
        prompt_file: str | None = None,
        session_id: str | None = None,
    ) -> list[str]:
        raise NotImplementedError

    def cleanup_session_argv(self, *, binary: str, session_id: str) -> list[str] | None:
        """Argv to delete a persisted session, or None if nothing to delete."""
        return None

    def extract_text(self, stdout: str) -> str:
        """Pull the model reply text out of vendor JSON (or return raw stdout)."""
        text = stdout.strip()
        if not text:
            return ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Streaming / multi-line JSON: try last JSON object line.
            data = _last_json_line(text)
            if data is None:
                return text
        return _unwrap_vendor_result(data, fallback=text)


@dataclass(frozen=True)
class GrokCliBackend(CliBackend):
    name: str = "grok"
    binary: str = "grok"
    prompt_mode: PromptMode = "file"
    install_hint: str = (
        "Install Grok Build and authenticate, then retry. "
        "See https://docs.x.ai/ or `grok --help`."
    )

    def allocate_session_id(self) -> str | None:
        # Grok always persists sessions; pin an id so we can delete it after.
        return str(uuid.uuid4())

    def build_argv(
        self,
        *,
        binary: str,
        model: str,
        system: str | None,
        prompt: str,
        prompt_file: str | None = None,
        session_id: str | None = None,
    ) -> list[str]:
        argv = [
            binary,
            "--output-format", "json",
            "--tools", "",
            "-m", model,
        ]
        if session_id:
            argv.extend(["--session-id", session_id])
        if system:
            argv.extend(["--system-prompt-override", system])
        if prompt_file:
            argv.extend(["--prompt-file", prompt_file])
        else:
            argv.extend(["-p", prompt])
        return argv

    def cleanup_session_argv(self, *, binary: str, session_id: str) -> list[str] | None:
        return [binary, "sessions", "delete", session_id]


@dataclass(frozen=True)
class ClaudeCliBackend(CliBackend):
    name: str = "claude"
    binary: str = "claude"
    prompt_mode: PromptMode = "stdin"
    install_hint: str = (
        "Install Claude Code and run `claude auth`, then retry. "
        "See https://docs.anthropic.com/en/docs/claude-code"
    )

    def build_argv(
        self,
        *,
        binary: str,
        model: str,
        system: str | None,
        prompt: str,
        prompt_file: str | None = None,
        session_id: str | None = None,
    ) -> list[str]:
        # -p with no prompt arg: read prompt from stdin.
        # --no-session-persistence: do not write the chat to disk (print mode only).
        argv = [
            binary,
            "-p",
            "--output-format", "json",
            "--tools", "",
            "--model", model,
            "--permission-mode", "dontAsk",
            "--no-session-persistence",
        ]
        if system:
            argv.extend(["--system-prompt", system])
        return argv

    def extract_text(self, stdout: str) -> str:
        text = stdout.strip()
        if not text:
            return ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = _last_json_line(text)
            if data is None:
                return text
        # Claude --output-format json: {"type":"result","result":"...", "is_error":...}
        if isinstance(data, dict) and "result" in data:
            if data.get("is_error"):
                err = data.get("result") or data.get("terminal_reason") or "claude CLI error"
                raise RuntimeError(f"claude CLI reported an error: {err}")
            result = data["result"]
            return result if isinstance(result, str) else json.dumps(result)
        return _unwrap_vendor_result(data, fallback=text)


@dataclass(frozen=True)
class CodexCliBackend(CliBackend):
    name: str = "codex"
    binary: str = "codex"
    prompt_mode: PromptMode = "stdin"
    install_hint: str = (
        "Install the Codex CLI and run `codex login`, then retry. "
        "See https://github.com/openai/codex"
    )

    def build_argv(
        self,
        *,
        binary: str,
        model: str,
        system: str | None,
        prompt: str,
        prompt_file: str | None = None,
        session_id: str | None = None,
    ) -> list[str]:
        # `codex exec` is non-interactive. `-` means read prompt from stdin.
        # --ephemeral: do not persist session files.
        argv = [
            binary, "exec",
            "-m", model,
            "--skip-git-repo-check",
            "--json",
            "--ephemeral",
            "-s", "read-only",
            "-",
        ]
        if system:
            # Fold system into the prompt at the completer layer for codex.
            pass
        return argv

    def extract_text(self, stdout: str) -> str:
        """Codex --json emits JSONL events; prefer last agent message."""
        text = stdout.strip()
        if not text:
            return ""
        last_message: str | None = None
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            # Common shapes across codex versions.
            etype = event.get("type") or event.get("event")
            if etype in {"item.completed", "message", "agent_message", "turn.completed"}:
                item = event.get("item") or event.get("message") or event
                if isinstance(item, dict):
                    content = item.get("text") or item.get("content") or item.get("message")
                    if isinstance(content, str) and content.strip():
                        last_message = content
                    elif isinstance(content, list):
                        parts = []
                        for part in content:
                            if isinstance(part, dict) and isinstance(part.get("text"), str):
                                parts.append(part["text"])
                            elif isinstance(part, str):
                                parts.append(part)
                        if parts:
                            last_message = "".join(parts)
            if etype in {"error", "turn.failed"} and event.get("error"):
                raise RuntimeError(f"codex CLI error: {event.get('error')}")
        if last_message is not None:
            return last_message
        # Fallback: whole stdout as text.
        return text


def backend_for_provider(provider) -> CliBackend:
    from nori.providers import Provider

    if provider is Provider.GROK_CLI:
        return GrokCliBackend()
    if provider is Provider.CLAUDE_CLI:
        return ClaudeCliBackend()
    if provider is Provider.CODEX_CLI:
        return CodexCliBackend()
    raise ValueError(f"Not a CLI provider: {provider!r}")


def write_prompt_file(prompt: str) -> Path:
    """Write prompt to a temp file; caller must delete when done."""
    fd, path = tempfile.mkstemp(prefix="nori-cli-prompt-", suffix=".txt")
    p = Path(path)
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(prompt)
    except Exception:
        p.unlink(missing_ok=True)
        raise
    return p


def _last_json_line(text: str) -> dict | list | None:
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, (dict, list)):
            return data
    return None


def _unwrap_vendor_result(data, *, fallback: str) -> str:
    if isinstance(data, str):
        return data
    if not isinstance(data, dict):
        return fallback
    for key in ("result", "content", "message", "text", "response", "output"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val
        if isinstance(val, dict):
            nested = val.get("content") or val.get("text")
            if isinstance(nested, str):
                return nested
    # Model may have returned our envelope at the top level.
    if "tool_calls" in data or ("content" in data and len(data) <= 3):
        return json.dumps(data)
    return fallback
