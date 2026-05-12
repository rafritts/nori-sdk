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
NORI_CLI_MODEL=grok-4
```

Or pass them as flags:

```bash
nori --provider xai --model grok-4 "What is today's date?"
```

---

## Flags

| Flag | Default | Description |
|---|---|---|
| `--provider` | `$NORI_CLI_PROVIDER` | Provider name (`xai`, `openai`, `anthropic`) |
| `--model` | `$NORI_CLI_MODEL` | Model ID |
| `--repl` | off | Stay in a conversation loop after each response |
| `--no-narration` | off | Suppress real-time tool call narration |
| `--no-sandbox` | off | Allow tools to access paths outside the current directory |

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

By default, file and shell tools are sandboxed to the current working directory. Pass `--no-sandbox` to allow unrestricted access:

```bash
nori --no-sandbox "Check my SSH config at ~/.ssh/config"
```

---

## What the CLI agent has

The CLI agent runs with `Bash` always loaded, and these tools available on demand (deferred):

- `ApiClient`, `BrowserAgent`, `BrowserClient`, `CodeRunner`
- `FileEdit`, `FileSearch`, `WebClient`, `WebSearch`

It's designed to handle ad-hoc tasks — inspecting files, running commands, fetching data, exploring a codebase. For production use, build an `Agent` in code with the specific tools and configuration your application needs.
