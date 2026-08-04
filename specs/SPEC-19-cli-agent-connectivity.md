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

**Use the CLI for connectivity. Do not use the CLI as an agent, and do not expose it as a Nori tool.**

| Layer | Who owns it |
|---|---|
| Auth / transport to the model | The installed CLI (subscription, OAuth, local login) |
| Agentic loop, tools, permissions, narration, sandbox | **Nori** |
| Built-in tools of Grok / Claude / Codex (Bash, Edit, …) | **Disabled** — never invoked on Nori's behalf |

Nori does **not** wrap `grok` / `claude` / `codex` as tools the model can call (not `Bash`-style, not agent-as-tool). Those CLIs are alternative **model backends**, in the same conceptual slot as `Provider.XAI` or `Provider.BEDROCK`.

After setup, application code is unchanged:

```python
from nori import Agent, Model, Provider
from nori.tools import Bash, FileRead, WebSearch

agent = Agent(
    name="assistant",
    model=Model(id="grok-4.5", provider=Provider.GROK_CLI),
    tools=[Bash, FileRead, WebSearch],
)
await agent.run("Summarize the top-level modules in this repo")
```

The only difference is *how* each completion is obtained.

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

For every Nori completion turn, the CLI is invoked **once**, headless, with **its own agent tools off**. Nori then parses the model reply and, if the reply contains tool calls for *Nori* tools, runs those tools itself and loops.

#### Shared rules

1. **Resolve binary** via `shutil.which`. If missing, raise a clear error with install/login hints.
2. **Disable CLI-native tools** so the subprocess is model I/O only, not a nested agent.
3. **Pass model id** with `-m` / `--model` when set.
4. **Prefer structured stdout** (`json` / equivalent) over plain text so tool-call intent can be parsed reliably.
5. **Timeouts** honor `Agent` / config run timeouts (kill the subprocess on cancel/timeout).
6. **cwd** defaults to the process cwd (same as Nori tools). Optional later: `Model.cli_cwd`.
7. **stderr** is logged at debug and included in error messages on non-zero exit; it is not mixed into the completion content.
8. **No API key check** in `Model.__post_init__` for CLI providers (same idea as Bedrock / `http_client`).

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
{system content}

[conversation]
user: ...
assistant: ...
tool (id=…, name=…): ...
user: ...

[nori tools]   # only when tools are non-empty
You may call Nori tools by replying with ONLY a JSON object of the form:
{"tool_calls":[{"id":"call_1","name":"Bash","arguments":{"command":"ls"}}]}
or a final answer:
{"content":"..." }

Available tools:
{json schema list}
```

Exact envelope is an implementation detail, but it must be:

- **Deterministic** and covered by unit tests with fixtures
- **Round-trippable** into `ChatCompletionMessage.tool_calls` / `.content`
- Prefer **`--json-schema`** (Grok/Claude) when available to constrain the model to the envelope

Multi-turn Nori history (including prior tool results) is folded into this prompt each turn. The CLI process is **stateless from Nori's perspective** — no reliance on CLI session resume for the agent loop (avoids double history and stuck sessions). Optional future: session reuse for cache/latency; not v1.

### 4. Tool calling strategy

| Concern | Behavior |
|---|---|
| CLI built-in tools | Always off |
| Nori tools | Encoded in the prompt (and/or json-schema); model emits structured tool_calls; Nori executes |
| `tool_choice` | Best-effort: `"none"` → instruct final text only; forced function → instruct that tool; `"auto"` → default envelope |
| Parallel tool calls | Supported in the JSON envelope if the model emits multiple; same as HTTP path |
| Images / multimodal | Out of scope for v1 unless a CLI flag is trivial (`codex -i`, etc.) — document as follow-up |

If parsing fails (model returns prose instead of the envelope), treat the whole stdout as `content` text (graceful degrade), and log a warning. Do not crash the loop.

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
- Envelope parse: content-only, single tool call, multi tool call, malformed → content fallback
- `Model(provider=Provider.GROK_CLI)` does not require API key
- Agent loop with fake `CliCompleter`: one tool call then final answer

Integration (optional, `@pytest.mark.integration`, skip if binary absent):

- `grok -p` / `claude -p` smoke: one-shot “reply with the word pong”

### 7. Docs

- Short section in `docs/getting-started.md` or `docs/agent.md`: “Using installed CLIs instead of API keys”
- Note cost/usage limitations and ToS caveat
- Codex `-p` ≠ print (avoid footgun in docs)

---

## Rollout

| Phase | Scope |
|---|---|
| **v1** | `GROK_CLI` + `CLAUDE_CLI` with tools-disabled headless + JSON envelope tool calling; completer abstraction; unit tests |
| **v1.1** | `CODEX_CLI` once tool-disable / final-message capture is reliable |
| **Later** | Multimodal pass-through, session reuse / prompt cache, streaming narration from CLI stdout, `cli_path` overrides |

Ship Grok + Claude first — both have clear `-p` and `--tools ""`. Codex follows once the exec path is proven.

---

## Open questions

1. **Codex tool suppression** — Is there a supported way to run `codex exec` with zero agent tools (model text only)? If not, should v1 omit `CODEX_CLI` or accept “Codex may still try tools under sandbox”?
2. **System prompt flags** — Grok `--system-prompt-override` vs Claude `--system-prompt` vs Codex config: confirm best flags so Nori's system prompt is not double-wrapped with CLI defaults (`--bare` / empty tools helps).
3. **JSON envelope vs vendor json-schema** — Prefer forcing schema via CLI flags when present; fall back to prompt-only instructions. Confirm Grok/Claude json-schema works with tools disabled and multi-turn serialized prompts.
4. **Latency** — Cold-starting a CLI per turn is slower than HTTP keep-alive. Acceptable for v1? (Later: long-lived `grok agent stdio` / local proxy.)
5. **ToS / Acceptable use** — Whether automating subscription CLIs is allowed varies by vendor. Spec treats this as user responsibility; any stronger stance (warn at runtime once)?
6. **`nori` CLI default** — Keep default as `Provider.XAI` + API key, or document `NORI_PROVIDER=grok_cli` as the zero-key path?

---

## Success criteria

- With `claude` (or `grok`) installed and authenticated, and **no** corresponding API key in the environment, a Nori `Agent` configured with `Provider.CLAUDE_CLI` / `Provider.GROK_CLI` can complete a multi-turn run that uses **Nori** tools (`Bash`, etc.).
- The CLI process never executes its own Edit/Bash/etc. on Nori's behalf (tools disabled in argv).
- HTTP providers and existing demos behave exactly as before.
- Missing binary and auth failures produce actionable errors, not stack traces from `AsyncOpenAI`.
