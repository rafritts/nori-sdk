# SPEC-19: CLI Agent Connectivity Providers

## Problem

Nori talks to models through the OpenAI-compatible HTTP API (`AsyncOpenAI` + `api_key` / `base_url`). That requires a provider API key (`XAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, …).

Many developers already have a working path to those same models without an API key:

| CLI | Headless invocation | Auth model |
|---|---|---|
| **Grok Build** | `grok -p` / `grok --single` | logged-in Grok / xAI session |
| **Claude Code** | `claude -p` / `claude --print` | Claude Pro/Max (or API) via `claude auth` |
| **Codex** | `codex exec` *(not `-p` — that is profile)* | ChatGPT / Codex login |

Today, if someone has `grok` installed and authenticated but no `XAI_API_KEY`, Nori cannot use that connectivity. They either mint an API key (separate billing) or cannot run Nori at all.

---

## Design principle

**Use the CLI for connectivity only. Zero tools — vendor or Nori.**

| Layer | Who owns it |
|---|---|
| Auth / transport to the model | The installed CLI (subscription, OAuth, local login) |
| Single-shot / multi-turn text completion | **Nori** agent loop (no tool turns) |
| Built-in tools of Grok / Claude / Codex (Bash, Edit, …) | **Disabled** — `--tools ""` + aggressive system ban |
| Nori tools / MCP / deferred tools / scratchpad tools | **Forbidden** — Agent construction raises if any are registered |

Nori does **not** wrap `grok` / `claude` / `codex` as tools, and does **not** encode a Nori tool-call envelope through them. Those CLIs are alternative **model backends** for text completion, in the same conceptual slot as `Provider.XAI` or `Provider.BEDROCK`, but **without tool calling**.

```python
from nori import Agent, Model, Provider

# Text-only. Passing tools=... raises ValueError.
agent = Agent(
    name="assistant",
    model=Model(id="grok-4.5", provider=Provider.GROK_CLI),
)
await agent.run("Explain what a completion backend is in one paragraph")
```

If the agent needs tools, use an HTTP provider (`Provider.XAI`, etc.) with an API key.

---

## Solution

### 1. Three CLI providers

Add first-class `Provider` entries (same pattern as `Provider.BEDROCK` — special setup, no env API key):

```python
class Provider(Enum):
    ...
    # CLI connectivity backends — no API key; binary must be on PATH and authenticated.
    # value = (binary_name, None)  — base_url unused; api_key env unused
    GROK_CLI   = ("grok",   None)
    CLAUDE_CLI = ("claude", None)
    CODEX_CLI  = ("codex",  None)
```

| Provider | Binary | Default headless command shape |
|---|---|---|
| `GROK_CLI` | `grok` | `grok -p <prompt> -m <model> --tools "" --output-format json` |
| `CLAUDE_CLI` | `claude` | `claude -p <prompt> --model <model> --tools "" --output-format json` |
| `CODEX_CLI` | `codex` | `codex exec -m <model> --json …` *(exact tool-disable flags TBD; see Open questions)* |

Model IDs are whatever the underlying CLI accepts (`-m` / `--model`). Nori does not alias or rewrite them.

### 2. Completer abstraction

Today `Agent._complete` always calls `self._client.chat.completions.create(...)`. CLI backends do not speak HTTP, so introduce a thin backend interface used only at the completion boundary:

```python
# nori/completer.py (sketch)

class Completer(Protocol):
    async def complete(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        extra_headers: dict[str, str] | None = None,
        **kwargs,
    ) -> ChatCompletionMessage:
        """Return an OpenAI-shaped assistant message (content and/or tool_calls)."""
```

- **HTTP path (existing):** `OpenAICompleter` wraps `AsyncOpenAI` — current behavior, zero regression.
- **CLI path (new):** `CliCompleter` shells out to the configured binary, parses stdout into the same `ChatCompletionMessage` shape.

`Agent` picks the completer from `Model` at first use. Summarizer and other internal callers that currently take `AsyncOpenAI` should take a `Completer` (or keep a thin adapter) so CLI backends work for summarization too.

This is an **internal** seam. Public API stays `Model` + `Provider`; users do not construct completers.

### 3. CLI invocation contract

For every Nori completion turn, the CLI is invoked **once**, headless, with **all tools off**. The reply is treated as **final text only**. Any `tool_calls` in the payload are stripped and never executed.

#### Shared rules

1. **Resolve binary** via `shutil.which`. If missing, raise a clear error with install/login hints.
2. **Disable CLI-native tools** (`--tools ""` where available) so the subprocess is model I/O only.
3. **Inject an aggressive system ban**: no tool calling of any kind — not vendor tools, not Nori tools, not invented tools. Plain text only.
4. **Agent construction rejects tools**: `tools`, `deferred_tools`, `mcp_servers`, `scratchpad`, `self_modify`, and `force_tool` raise `ValueError` on CLI providers.
5. **Pass model id** with `-m` / `--model` when set.
6. **Prefer structured stdout** (`json` / equivalent) over plain text when available; parse for `content` only.
7. **Timeouts** honor `Agent` / config run timeouts (kill the subprocess on cancel/timeout).
8. **cwd** defaults to the process cwd. Optional later: `Model.cli_cwd`.
9. **stderr** is logged at debug and included in error messages on non-zero exit; it is not mixed into the completion content.
10. **No API key check** in `Model.__post_init__` for CLI providers (same idea as Bedrock / `http_client`).

#### Per-CLI sketch (implementation may adjust flags as CLIs evolve)

**Grok**

```bash
grok -p "$PROMPT" \
  -m "$MODEL" \
  --tools "" \
  --output-format json \
  --system-prompt-override "$SYSTEM"   # when Nori supplies a system prompt
  # optional: --json-schema ... for structured tool-call envelopes
```

Notes: Grok's `-p` / `--single` is single-turn print-and-exit. `--tools ""` (or equivalent full disallow list) must prevent Grok from running its own tools. Prefer `--verbatim` if prompt wrapping interferes with our serialization.

**Claude**

```bash
claude -p "$PROMPT" \
  --model "$MODEL" \
  --tools "" \
  --output-format json \
  --system-prompt "$SYSTEM" \
  --permission-mode dontAsk   # or equivalent non-interactive mode
  # optional: --json-schema ... ; --bare for minimal session chrome
```

Notes: Claude documents `--tools ""` as disabling all built-in tools. That is the key flag for this design.

**Codex**

```bash
codex exec -m "$MODEL" --json --skip-git-repo-check \
  -o /tmp/nori-codex-last.txt \
  "$PROMPT"
```

Notes: Codex does **not** use `-p` for print mode (`-p` is config profile). Non-interactive entry point is `codex exec`. Tool-disable story is weaker/less documented than Grok/Claude — v1 may start with “last message only + prompt-encoded tools” or require a documented sandbox/profile that cannot run tools. Capture final text via `-o` / JSONL event stream.

#### Prompt serialization

CLI headless modes generally take a **single prompt string** (plus optional system override), not a full OpenAI messages array. Nori therefore serializes `messages` into one prompt for each completion:

```
[system]
{TOOLS FORBIDDEN ban}
{user system content}

[conversation]
user: ...
assistant: ...

[output contract]
TOOLS ARE BANNED. Plain text only.
```

Rules:

- **Never** serialize tool schemas, tool_choice, or a Nori tool envelope
- **Never** re-emit historical `tool_calls` / `role=tool` messages into the prompt
- Prefer plain text answers; if the model returns `{"content":"..."}` JSON, take `content` only
- If the model still emits `tool_calls`, **strip them** and do not execute

Multi-turn Nori history (user/assistant text only) is folded into this prompt each turn. The CLI process is **stateless from Nori's perspective** — no reliance on CLI session resume for the agent loop. Optional future: session reuse for cache/latency; not v1.

### 4. Tool calling strategy

| Concern | Behavior |
|---|---|
| CLI built-in tools | Always off (`--tools ""` + system ban) |
| Nori tools | **Not allowed** — Agent raises if registered; completer drops schemas |
| `tool_choice` | Ignored on CLI path |
| Parsed `tool_calls` | Stripped; never executed |
| Images / multimodal | Out of scope for v1 unless a CLI flag is trivial — document as follow-up |

If parsing fails (model returns prose), treat the whole stdout as `content` text. Do not crash the loop.

### 5. Config and errors

```python
import nori
from nori import Model, Provider

nori.configure(
    model=Model(id="claude-opus-4-7", provider=Provider.CLAUDE_CLI),
)
```

**Missing binary:**

```
Provider.CLAUDE_CLI requires the `claude` CLI on PATH, but it was not found.
Install Claude Code and run `claude auth` (or equivalent), then retry.
```

**Non-zero exit / auth failure:** surface stderr snippet + exit code. Do not silently fall back to API keys.

**Optional (error-message only, not auto-switch):** when a normal provider fails with “no API key”, the message may *mention* CLI providers as an alternative. Auto-fallback is **out of scope** — explicit `Provider.*_CLI` only.

### 6. Cost / usage

CLI subscription usage is billed by the vendor's plan, not by Nori's static price table. For CLI providers:

- `cost_for()` returns `0.0` (same treatment as Ollama / unknown models)
- Token counters: populate when JSON output includes usage; otherwise leave at 0
- Document clearly: `agent.cost` is not meaningful for CLI-backed runs

### 7. Security

- Subprocess only with fixed argv templates + user/model-derived strings passed as arguments or stdin — never `shell=True`.
- CLI binaries are trusted the same way the user trusts having them installed (they already have full user privileges if misused interactively).
- Nori still applies its own **Permissions** / sandbox to *Nori* tools; the CLI is not given Nori tool power.
- Do not pass secrets into prompts beyond what the conversation already contains.

---

## API summary

```python
from nori import Agent, Model, Provider
from nori.tools import Bash, FileSearch

# Grok installed + logged in, no XAI_API_KEY
agent = Agent(
    name="dev",
    model=Model(id="grok-4.5", provider=Provider.GROK_CLI),
    tools=[Bash, FileSearch],
)

# Claude Code subscription
agent = Agent(
    name="dev",
    model=Model(id="claude-sonnet-4-6", provider=Provider.CLAUDE_CLI),
    tools=[Bash, FileSearch],
)

# Codex CLI
agent = Agent(
    name="dev",
    model=Model(id="gpt-5.4", provider=Provider.CODEX_CLI),
    tools=[Bash, FileSearch],
)
```

CLI providers are also valid in `nori.configure(model=...)` and `tool_models={...}`.

Nori's own CLI (`nori --provider grok_cli --model grok-4.5 "…"`) should accept the new provider names via the existing `Provider[name.upper()]` path.

---

## What this is not

| Non-goal | Why |
|---|---|
| Grok/Claude/Codex as Nori **tools** | User wants connectivity, not nested agents |
| Running the CLI's full agent loop as a substitute for Nori | Nori owns tools, permissions, narration, anti-spin, etc. |
| Depending on third-party “Claude Max → OpenAI proxy” servers | Optional user setup already works via `base_url`; Nori should call CLIs directly |
| Auto-detecting a CLI when an API key is missing | Too magical; explicit provider only |
| Perfect parity with HTTP streaming / exact native tool_call IDs | Best-effort structured envelope is enough for v1 |
| Guaranteeing vendor ToS compliance for subscription→automation use | Document as user responsibility; CLIs and plans change |

---

## Implementation plan

### 1. `nori/providers.py`

Add `GROK_CLI`, `CLAUDE_CLI`, `CODEX_CLI`. Extend `Model.__post_init__` so these skip API key validation (like Bedrock).

### 2. `nori/completer.py` (new)

- `Completer` protocol
- `OpenAICompleter` — move current `chat.completions.create` path here
- `CliCompleter` — binary resolve, argv build, subprocess, parse

### 3. `nori/cli_backends.py` (new)

Per-backend small adapters:

```python
@dataclass(frozen=True)
class CliBackend:
    name: str
    binary: str
    def build_argv(self, *, model: str, system: str | None, prompt: str, json_schema: dict | None) -> list[str]: ...
    def parse_stdout(self, stdout: str) -> ChatCompletionMessage: ...
```

Implementations: `GrokCliBackend`, `ClaudeCliBackend`, `CodexCliBackend`.

Keep flag tables in one place so CLI churn is easy to patch.

### 4. `nori/model.py`

- Recognize CLI providers in `__post_init__`
- Optional fields if needed later: `cli_path: str | None = None` (override binary path), `cli_extra_args: list[str] | None = None`
- v1 can ship without extra fields if PATH resolution is enough

### 5. `nori/agent.py` (+ summarizer)

- Build completer from model instead of only `AsyncOpenAI`
- `_complete` calls `completer.complete(...)`
- Propagate cancel/timeout to subprocess

### 6. Tests

Unit (mocked subprocess):

- Binary missing → clear error
- Argv construction per backend (tools disabled, model flag, output format)
- Parse: content-only; tool_calls stripped; malformed → content fallback
- Aggressive no-tools ban present in system + body
- `Model(provider=Provider.GROK_CLI)` does not require API key
- Agent with CLI provider rejects `tools=` / registers empty tool map
- Agent loop with fake `CliCompleter`: plain text final answer, no tools passed

Integration (optional, `@pytest.mark.integration`, skip if binary absent):

- `grok -p` / `claude -p` smoke: one-shot “reply with the word pong”

### 7. Docs

- Short section in `docs/getting-started.md` or `docs/agent.md`: “Using installed CLIs instead of API keys” (text-only)
- Note cost/usage limitations and ToS caveat
- Codex `-p` ≠ print (avoid footgun in docs)

---

## Rollout

| Phase | Scope |
|---|---|
| **v1** | `GROK_CLI` + `CLAUDE_CLI` + `CODEX_CLI` with **zero tools** (argv + system ban + Agent refuse tools); completer abstraction; unit tests |
| **Later** | Multimodal pass-through, session reuse / prompt cache, streaming narration from CLI stdout, `cli_path` overrides |

Ship Grok + Claude first — both have clear `-p` and `--tools ""`. Codex follows once the exec path is proven.

---

## Open questions

1. **Codex tool suppression** — Is there a supported way to run `codex exec` with zero agent tools (model text only)? If not, rely on prompt ban + strip tool_calls.
2. **System prompt flags** — Grok `--system-prompt-override` vs Claude `--system-prompt` vs Codex config: confirm best flags so Nori's system prompt is not double-wrapped with CLI defaults (`--bare` / empty tools helps).
3. **Latency** — Cold-starting a CLI per turn is slower than HTTP keep-alive. Acceptable for v1? (Later: long-lived `grok agent stdio` / local proxy.)
4. **ToS / Acceptable use** — Whether automating subscription CLIs is allowed varies by vendor. Spec treats this as user responsibility; any stronger stance (warn at runtime once)?
5. **`nori` CLI default** — Keep default as `Provider.XAI` + API key, or document `NORI_PROVIDER=grok_cli` as the zero-key path?

---

## Success criteria

- With `claude` (or `grok`) installed and authenticated, and **no** corresponding API key in the environment, a Nori `Agent` configured with `Provider.CLAUDE_CLI` / `Provider.GROK_CLI` can complete a **text-only** multi-turn run.
- `Agent(..., tools=[...], model=Model(..., provider=Provider.GROK_CLI))` raises — no tools registered.
- The CLI process never executes its own Edit/Bash/etc. on Nori's behalf (tools disabled in argv + model ban).
- HTTP providers and existing demos behave exactly as before.
- Missing binary and auth failures produce actionable errors, not stack traces from `AsyncOpenAI`.
