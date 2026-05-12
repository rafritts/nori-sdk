# SPEC-12: Nori CLI

## Goal

Add a `nori` CLI entry point so developers can fire off agent prompts from the terminal without writing Python. It's a testing tool — not a product — so it should stay thin.

## Usage

```bash
# Basic
nori "What is the weather in Ashburn, VA?"

# Override provider/model for one run
nori --provider xai --model grok-4.3 "Summarize this file" < notes.txt

# Defaults from env (set in .env or shell)
NORI_PROVIDER=xai NORI_MODEL=grok-4.3 nori "What is the capital of France?"
```

## Config

No config file. Config comes from two places, in priority order:

1. **CLI flags** — `--provider`, `--model`
2. **Env vars** — `NORI_PROVIDER`, `NORI_MODEL` (picked up from `.env` via python-dotenv, same as the SDK)

Defaults when neither is set: `Provider.XAI`, `grok-4.3`.

The vocabulary is identical to the Python API (`Provider.XAI` → `--provider xai`, `Model(id="grok-4.3", ...)` → `--model grok-4.3`), so the mental translation back to Python is obvious.

## Default Tools

The CLI agent gets a practical set for testing:

- `WebSearch` — keyword search
- `ApiClient` — raw HTTP calls
- `WebClient` — fetch/scrape pages

No file tools, no shell tools. Developers testing those things should write a script.

## Output

Stream the agent's final response text to stdout. Tool calls and intermediate steps are suppressed — clean output suitable for piping.

## Implementation

### 1. `nori/cli.py`

New module. Parses args, resolves provider/model, builds an `Agent`, runs it, prints the result. ~50 lines.

### 2. `pyproject.toml`

Add entry point:

```toml
[project.scripts]
nori = "nori.cli:main"
```

### 3. No new dependencies

`argparse` is stdlib. Everything else is already in the package.

## What's Out of Scope

- `nori config` subcommand — not needed, env vars cover it
- `nori chat` interactive REPL — out of scope for now
- Configurable tool sets — hardcoded defaults are fine for a dev tool
- Rich formatting / color output — plain text, pipeable

## Open Questions

None. This is small enough to just build.
