"""Completion backends: OpenAI-compatible HTTP and CLI connectivity.

Internal seam used by Agent. Users configure Model/Provider only.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass
from typing import Any, Protocol

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessage

from nori.cli_backends import CliBackend, backend_for_provider, write_prompt_file

logger = logging.getLogger("nori.completer")


@dataclass
class CompletionResult:
    message: ChatCompletionMessage
    usage: Any | None = None


class Completer(Protocol):
    async def complete(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        extra_headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> CompletionResult: ...


class OpenAICompleter:
    """Wraps AsyncOpenAI chat.completions.create."""

    def __init__(self, client: AsyncOpenAI) -> None:
        self._client = client

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        extra_headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> CompletionResult:
        req: dict[str, Any] = {"model": model, "messages": messages, **kwargs}
        if tools is not None:
            req["tools"] = tools
        if tool_choice is not None:
            req["tool_choice"] = tool_choice
        if extra_headers:
            req["extra_headers"] = extra_headers
        response = await self._client.chat.completions.create(**req)
        return CompletionResult(
            message=response.choices[0].message,
            usage=getattr(response, "usage", None),
        )


class CliCompleter:
    """Shell out to grok/claude/codex for model connectivity only.

    No tools of any kind: vendor CLI tools are disabled in argv, Nori tools are
    never serialized, and any tool_calls in the reply are stripped.
    """

    def __init__(
        self,
        backend: CliBackend,
        *,
        binary_path: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.backend = backend
        path = binary_path or shutil.which(backend.binary)
        if not path:
            raise FileNotFoundError(
                f"Provider requires the `{backend.binary}` CLI on PATH, but it was not found.\n"
                f"{backend.install_hint}"
            )
        self.binary_path = path
        self.timeout = timeout

    @classmethod
    def from_model(cls, model, *, timeout: float | None = None) -> "CliCompleter":
        if model.provider is None or not model.provider.is_cli:
            raise ValueError("CliCompleter.from_model requires a CLI provider")
        backend = backend_for_provider(model.provider)
        return cls(backend, binary_path=model.cli_path, timeout=timeout)

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        extra_headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> CompletionResult:
        # Hard ban: ignore tools / tool_choice entirely. CLI path is text only.
        if tools:
            logger.warning(
                "cli_completer: dropping %d tool schema(s) — CLI connectivity forbids tools",
                len(tools),
            )
        system, user_prompt = serialize_for_cli(messages)
        # Codex has no system flag — fold into the prompt body.
        if self.backend.name == "codex" and system:
            user_prompt = f"[system]\n{system}\n\n{user_prompt}"
            system = None

        prompt_file = None
        stdin_data: str | None = None
        try:
            if self.backend.prompt_mode == "file":
                prompt_file = write_prompt_file(user_prompt)
                argv = self.backend.build_argv(
                    binary=self.binary_path,
                    model=model,
                    system=system,
                    prompt=user_prompt,
                    prompt_file=str(prompt_file),
                )
            elif self.backend.prompt_mode == "stdin":
                stdin_data = user_prompt
                argv = self.backend.build_argv(
                    binary=self.binary_path,
                    model=model,
                    system=system,
                    prompt=user_prompt,
                )
            else:
                argv = self.backend.build_argv(
                    binary=self.binary_path,
                    model=model,
                    system=system,
                    prompt=user_prompt,
                )

            logger.debug("cli_complete binary=%s argv0=%s", self.binary_path, argv[:4])
            stdout, stderr, code = await _run_subprocess(
                argv, stdin_data=stdin_data, timeout=self.timeout
            )
            if code != 0:
                err = (stderr or stdout or "").strip()
                raise RuntimeError(
                    f"{self.backend.binary} exited with code {code}.\n{err[:2000]}"
                )
            raw = self.backend.extract_text(stdout)
            message = parse_cli_message(raw)
            return CompletionResult(message=message, usage=None)
        finally:
            if prompt_file is not None:
                try:
                    prompt_file.unlink(missing_ok=True)
                except OSError:
                    pass


# ── Serialization / parsing ───────────────────────────────────────────────────

# Always injected into the CLI system prompt. Flags like --tools "" are the hard
# control at the process boundary. This text is the model-facing ban — absolute.
_CLI_NO_TOOLS = """\
[Nori / CLI connectivity — TOOLS FORBIDDEN]

ABSOLUTE RULE: YOU HAVE NO TOOLS. TOOL CALLING IS COMPLETELY DISABLED.

This is not a preference. This is not optional. There are zero tools available.

- Do NOT call tools. Do NOT attempt tools. Do NOT emit tool_calls, function calls,
  tool_use blocks, XML tool tags, or any tool-shaped markup of any kind.
- Do NOT use Bash, Shell, Edit, Read, Write, Glob, Grep, WebSearch, WebFetch,
  Browser, Agent, MCP, Nori tools, or ANY other tool — vendor, framework, or invented.
- Do NOT run shell commands, edit files, browse the web, spawn subagents, or
  simulate a tool loop in prose.
- Do NOT reply with JSON envelopes that request tools. Do NOT invent tools.
- There is no tool API in this mode. There is no Nori tool envelope. Nothing.

You answer with plain text only. Write the final reply to the user and stop.

If you feel you need a tool: you still do not get one. Answer from what you know
in the prompt, or say what you cannot do. Never emit a tool call.
"""


def serialize_for_cli(messages: list[dict]) -> tuple[str | None, str]:
    """Return (system_prompt, user_blob) for a single CLI invocation.

    Tools are never serialized. CLI connectivity is text-only completion.
    """
    system_parts: list[str] = [_CLI_NO_TOOLS.strip()]
    conversation: list[str] = []

    for m in messages:
        role = m.get("role", "")
        content = _content_to_str(m.get("content"))
        if role == "system":
            if content:
                system_parts.append(content)
            continue
        if role == "user":
            conversation.append(f"user: {content}")
        elif role == "assistant":
            # Drop any historical tool_calls — tools do not exist on this path.
            conversation.append(f"assistant: {content}" if content else "assistant:")
        elif role == "tool":
            # Should not appear on a tool-free agent; ignore if present.
            continue
        else:
            conversation.append(f"{role}: {content}")

    system = "\n\n".join(system_parts)

    body_parts = [
        "[conversation]",
        "\n".join(conversation) if conversation else "(empty)",
        (
            "[output contract]\n"
            "TOOLS ARE BANNED. Reply with plain text only — your final answer to the user.\n"
            "No JSON tool envelopes. No tool_calls. No function calls. No markup for tools.\n"
            "Just write the answer."
        ),
    ]

    return system, "\n\n".join(body_parts)


def parse_cli_message(raw: str) -> ChatCompletionMessage:
    """Parse CLI stdout into a text-only ChatCompletionMessage.

    Any tool_calls in the payload are discarded. CLI connectivity never returns tools.
    """
    text = (raw or "").strip()
    if not text:
        return ChatCompletionMessage(role="assistant", content="")

    data = _loads_json_loose(text)
    if data is None:
        return ChatCompletionMessage(role="assistant", content=text)

    if not isinstance(data, dict):
        return ChatCompletionMessage(role="assistant", content=text)

    if data.get("tool_calls"):
        logger.warning("cli_completer: stripping tool_calls from CLI reply (tools forbidden)")

    content = data.get("content")
    if content is not None and not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)

    # Prefer explicit content field; otherwise treat whole object as opaque text
    # unless it only looked like a tool envelope (no useful content).
    if isinstance(content, str) and content.strip():
        return ChatCompletionMessage(role="assistant", content=content)

    if "content" in data and (content is None or content == ""):
        # Empty content with discarded tool_calls — nothing useful.
        if data.get("tool_calls"):
            return ChatCompletionMessage(
                role="assistant",
                content=(
                    "(CLI model attempted a tool call; tools are disabled on this "
                    "connectivity path. No tool was run.)"
                ),
            )
        return ChatCompletionMessage(role="assistant", content="")

    # Unknown JSON object — surface as text so the loop can continue.
    logger.warning("cli_completer: could not parse content field; using raw text")
    return ChatCompletionMessage(role="assistant", content=text)


def _content_to_str(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    parts.append(str(part.get("text", "")))
                else:
                    parts.append(json.dumps(part, ensure_ascii=False))
            else:
                parts.append(str(part))
        return "\n".join(parts)
    return str(content)


def _loads_json_loose(text: str) -> Any | None:
    """Parse JSON, tolerating markdown fences and leading/trailing prose."""
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        # drop first fence line and optional trailing fence
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # Find first {...} blob.
    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(s[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


async def _run_subprocess(
    argv: list[str],
    *,
    stdin_data: str | None = None,
    timeout: float | None = None,
) -> tuple[str, str, int]:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE if stdin_data is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(stdin_data.encode("utf-8") if stdin_data is not None else None),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        try:
            await proc.communicate()
        except Exception:
            pass
        raise TimeoutError(
            f"CLI subprocess timed out after {timeout}s: {argv[0]}"
        ) from None
    stdout = stdout_b.decode("utf-8", errors="replace") if stdout_b else ""
    stderr = stderr_b.decode("utf-8", errors="replace") if stderr_b else ""
    code = proc.returncode if proc.returncode is not None else 1
    if stderr.strip():
        logger.debug("cli_stderr binary=%s stderr=%s", argv[0], stderr[:500])
    return stdout, stderr, code
