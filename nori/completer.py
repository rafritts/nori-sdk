"""Completion backends: OpenAI-compatible HTTP and CLI connectivity.

Internal seam used by Agent. Users configure Model/Provider only.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageToolCall
from openai.types.chat.chat_completion_message_tool_call import Function

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
    """Shell out to grok/claude/codex for connectivity; Nori keeps the agent loop."""

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
        system, user_prompt = serialize_for_cli(messages, tools=tools, tool_choice=tool_choice)
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

_ENVELOPE_INSTRUCTIONS = """\
You are being driven by the Nori agent framework through a headless CLI.
Reply with ONLY a single JSON object (no markdown fences) in one of these forms:

Final answer (no tools):
{"content":"your user-facing reply"}

One or more Nori tool calls:
{"tool_calls":[{"id":"call_1","name":"ToolName","arguments":{...}}]}

Optional short status plus tools:
{"content":"brief status","tool_calls":[{"id":"call_1","name":"ToolName","arguments":{...}}]}

Do not invent tools that are not listed. Do not run shell commands yourself — call Nori tools.
Arguments must be a JSON object, not a string.
"""


def serialize_for_cli(
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    tool_choice: str | dict | None = None,
) -> tuple[str | None, str]:
    """Return (system_prompt, user_blob) for a single CLI invocation."""
    system_parts: list[str] = []
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
            line = f"assistant: {content}" if content else "assistant:"
            tcs = m.get("tool_calls")
            if tcs:
                calls = []
                for tc in tcs:
                    fn = tc.get("function") or {}
                    calls.append(
                        {
                            "id": tc.get("id"),
                            "name": fn.get("name"),
                            "arguments": _parse_args_blob(fn.get("arguments")),
                        }
                    )
                line += f"\ntool_calls: {json.dumps(calls, ensure_ascii=False)}"
            conversation.append(line)
        elif role == "tool":
            tid = m.get("tool_call_id", "")
            conversation.append(f"tool (id={tid}): {content}")
        else:
            conversation.append(f"{role}: {content}")

    system = "\n\n".join(system_parts) if system_parts else None

    body_parts = ["[conversation]", "\n".join(conversation) if conversation else "(empty)"]

    if tools:
        body_parts.append("[nori tools]")
        body_parts.append(_ENVELOPE_INSTRUCTIONS)
        if tool_choice == "none":
            body_parts.append(
                "tool_choice=none: you MUST reply with final content only "
                '(form {"content":"..."}); do not emit tool_calls.'
            )
        elif isinstance(tool_choice, dict):
            forced = (
                (tool_choice.get("function") or {}).get("name")
                if tool_choice.get("type") == "function"
                else None
            )
            if forced:
                body_parts.append(
                    f'tool_choice=required: you MUST call the Nori tool "{forced}" now '
                    f'(emit tool_calls with name "{forced}").'
                )
        schemas = []
        for t in tools:
            fn = t.get("function") if isinstance(t, dict) else None
            if not isinstance(fn, dict):
                continue
            schemas.append(
                {
                    "name": fn.get("name"),
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {}),
                }
            )
        body_parts.append("Available tools:")
        body_parts.append(json.dumps(schemas, indent=2, ensure_ascii=False))
    else:
        body_parts.append(
            'Reply with ONLY: {"content":"your reply"}  (single JSON object, no fences).'
        )

    return system, "\n\n".join(body_parts)


def parse_cli_message(raw: str) -> ChatCompletionMessage:
    """Parse CLI stdout (envelope or plain text) into ChatCompletionMessage."""
    text = (raw or "").strip()
    if not text:
        return ChatCompletionMessage(role="assistant", content="")

    data = _loads_json_loose(text)
    if data is None:
        return ChatCompletionMessage(role="assistant", content=text)

    if not isinstance(data, dict):
        return ChatCompletionMessage(role="assistant", content=text)

    # Already an OpenAI-ish message.
    if data.get("role") == "assistant" and ("content" in data or "tool_calls" in data):
        return _message_from_dict(data)

    content = data.get("content")
    if content is not None and not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)

    tool_calls_raw = data.get("tool_calls")
    tool_calls = _parse_tool_calls(tool_calls_raw) if tool_calls_raw else None

    if tool_calls or content is not None or "content" in data:
        return ChatCompletionMessage(
            role="assistant",
            content=content if isinstance(content, str) else None,
            tool_calls=tool_calls,
        )

    # Unknown JSON object — surface as text so the loop can continue.
    logger.warning("cli_completer: could not parse envelope; using raw text")
    return ChatCompletionMessage(role="assistant", content=text)


def _message_from_dict(data: dict) -> ChatCompletionMessage:
    content = data.get("content")
    if content is not None and not isinstance(content, str):
        content = str(content)
    tcs = _parse_tool_calls(data.get("tool_calls")) if data.get("tool_calls") else None
    return ChatCompletionMessage(role="assistant", content=content, tool_calls=tcs)


def _parse_tool_calls(raw) -> list[ChatCompletionMessageToolCall] | None:
    if not isinstance(raw, list) or not raw:
        return None
    out: list[ChatCompletionMessageToolCall] = []
    for i, tc in enumerate(raw):
        if not isinstance(tc, dict):
            continue
        # OpenAI shape: {id, type, function: {name, arguments}}
        if isinstance(tc.get("function"), dict):
            name = tc["function"].get("name") or ""
            args = tc["function"].get("arguments", {})
        else:
            name = tc.get("name") or ""
            args = tc.get("arguments", {})
        if not name:
            continue
        if isinstance(args, dict):
            args_str = json.dumps(args, ensure_ascii=False)
        elif isinstance(args, str):
            args_str = args
        else:
            args_str = json.dumps(args, ensure_ascii=False)
        call_id = tc.get("id") or f"call_{uuid.uuid4().hex[:8]}"
        out.append(
            ChatCompletionMessageToolCall(
                id=str(call_id),
                type="function",
                function=Function(name=str(name), arguments=args_str),
            )
        )
    return out or None


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


def _parse_args_blob(arguments) -> Any:
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            return json.loads(arguments)
        except json.JSONDecodeError:
            return arguments
    return arguments


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
