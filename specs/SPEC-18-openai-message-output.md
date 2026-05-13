# SPEC-18: OpenAI Message Output Format

## Motivation

`agent.run()` returns a plain `str` — the final assistant message content. This works for programmatic use, but it makes the agent incompatible with off-the-shelf chatbot software (Open WebUI, LibreChat, etc.) that expects responses in one of OpenAI's message formats.

The fix is an opt-in output mode that makes `run()` return an OpenAI-compatible `dict` instead of a string, without changing the default behavior for existing callers.

---

## Design

Add an `OutputFormat` enum to `nori/enums.py`:

```python
class OutputFormat(Enum):
    TEXT              = "text"               # default — returns str
    OPENAI_CHAT       = "openai_chat"        # Chat Completions message dict
    OPENAI_RESPONSES  = "openai_responses"   # Responses API message dict
```

Add `output_format: OutputFormat = OutputFormat.TEXT` to the `Agent` constructor.

### `OutputFormat.OPENAI_CHAT`

Targets the [Chat Completions API](https://platform.openai.com/docs/api-reference/chat) (`/v1/chat/completions`). Content is a plain string. Supported by nearly all off-the-shelf chatbot software.

```python
{"role": "assistant", "content": "4"}
```

### `OutputFormat.OPENAI_RESPONSES`

Targets the [Responses API](https://platform.openai.com/docs/api-reference/responses) (`/v1/responses`). Content is an array of typed blocks.

```python
{
    "role": "assistant",
    "content": [{"type": "output_text", "text": "4"}]
}
```

The return type of `run()` becomes `str | dict`. No other behavior changes.

---

## API

```python
from nori import Agent, OutputFormat

# Chat Completions format
agent = Agent(
    name="my-agent",
    model=...,
    output_format=OutputFormat.OPENAI_CHAT,
)
result = await agent.run("What is 2 + 2?")
# {"role": "assistant", "content": "4"}

# Responses API format
agent = Agent(
    name="my-agent",
    model=...,
    output_format=OutputFormat.OPENAI_RESPONSES,
)
result = await agent.run("What is 2 + 2?")
# {"role": "assistant", "content": [{"type": "output_text", "text": "4"}]}
```

---

## Changes

### `nori/enums.py`

Add `OutputFormat`:

```python
class OutputFormat(Enum):
    TEXT             = "text"
    OPENAI_CHAT      = "openai_chat"
    OPENAI_RESPONSES = "openai_responses"
```

Export it from `nori/__init__.py`.

### `nori/agent.py`

- Add `output_format: OutputFormat = OutputFormat.TEXT` constructor param.
- Store as `self.output_format`.
- In `run()`, after `result = await self._run_loop()`, apply formatting:

```python
if self.output_format == OutputFormat.OPENAI_CHAT:
    return {"role": "assistant", "content": result}
if self.output_format == OutputFormat.OPENAI_RESPONSES:
    return {"role": "assistant", "content": [{"type": "output_text", "text": result}]}
return result
```

- Update return type annotation: `-> str | dict`.

### Sub-agent calls

Sub-agents (invoked via tool `__call__`) always return `str` internally. The `output_format` setting on a parent agent does not propagate to sub-agents — sub-agents are internal and their callers expect strings. This is the correct behavior and requires no special handling.

---

## Out of Scope

- Streaming output in OpenAI SSE format — separate concern.
- Returning the full conversation history as a messages array — not needed for basic chatbot compatibility.
- Per-call format override on `run()` — the constructor param is sufficient.
