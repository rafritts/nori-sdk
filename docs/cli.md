# CLI

The Nori CLI is a prototyping tool. It's not a full-featured agent shell like Claude Code or Codex CLI — it's a fast way to fire an agent at a task and see what it can do, without writing any Python.

```bash
nori "What files are in /tmp?"
```

---

## Setup

The CLI needs a provider and model. Set them in your `.env` or as environment variables:

```bash
NORI_CLI_PROVIDER=xai
NORI_CLI_MODEL=grok-4.5
```

Or pass them as flags:

```bash
nori --provider xai --model grok-4.5 "What is today's date?"
```

Provider names are case-insensitive enum names (`xai`, `openai`, `anthropic`, `grok_cli`, `claude_cli`, `codex_cli`, …). See `Provider` in the library for the full list.

Without an API key, use a CLI connectivity provider if the vendor CLI is installed and logged in:

```bash
nori --provider grok_cli --model grok-4.5 "Summarize this repo in one paragraph"
```

CLI-backed runs are **text-only** — no tools. For tool-using CLI sessions, use an HTTP provider and API key.

---

## Flags

| Flag | Default | Description |
|---|---|---|
| `--provider` | `$NORI_CLI_PROVIDER` | Provider name (e.g. `xai`, `openai`, `grok_cli`) |
| `--model` | `$NORI_CLI_MODEL` | Model ID (e.g. `grok-4.5`) |
| `--repl` | off | Stay in a conversation loop after each response |
| `--no-narration` | off | Suppress real-time tool call narration |
| `--no-sandbox` | off | Allow tools to access paths outside the current directory |

`NORI_CLI_NO_SANDBOX=1` (or `true` / `yes`) is equivalent to `--no-sandbox`.

---

## REPL mode

```bash
nori --repl
```

Starts an interactive session. Type prompts at the `[::] ` prompt, press Enter to run. Type `exit` or `quit` to end the session. Conversation history is maintained across turns.

You can also combine a one-shot prompt with REPL mode — the prompt runs first, then the session continues:

```bash
nori --repl "Summarize the files in this directory"
```

---

## Sandbox

By default, file tools are sandboxed to the current working directory. Pass `--no-sandbox` to allow unrestricted path access for those tools:

```bash
nori --no-sandbox "Check my SSH config at ~/.ssh/config"
```

`Bash` and `CodeRunner` are **not** confined by the sandbox — see [Security](security.md).

---

## What the CLI agent has

With an HTTP provider, the CLI agent runs with `Bash` always loaded, and these tools available on demand (deferred, with stubs shown):

- `ApiClient`, `BrowserAgent`, `BrowserClient`, `CodeRunner`
- `FileEdit`, `FileSearch`, `WebClient`, `WebSearch`

With a CLI connectivity provider (`grok_cli` / `claude_cli` / `codex_cli`), the agent is text-only with no tools registered.

It's designed to handle ad-hoc tasks — inspecting files, running commands, fetching data, exploring a codebase. For production use, build an `Agent` in code with the specific tools and configuration your application needs.
