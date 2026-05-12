# SPEC-16: Git Tool

## Motivation

Coding agents are among the most common production use cases for agentic frameworks. Almost all of them involve git — reading history, staging changes, committing work, pushing branches. Right now agents use `Bash` for all of this, which works but has two problems:

1. Git commands mixed into `Bash` calls are invisible to the audit log as git operations — they appear as generic shell commands.
2. Destructive git operations (`reset --hard`, `push --force`, `branch -D`) are indistinguishable from safe ones at the permission layer. There's no way to allow `git status` but deny `git push --force` without parsing shell strings.

`Git` is a typed tool that exposes the git operations agents actually need, with destructive operations gated behind an explicit parameter.

---

## Design

### Single tool, operation-based dispatch

Rather than one tool per git command, `Git` takes an `operation` string and operation-specific parameters. This keeps the schema compact while making each operation explicit in the audit log.

```python
Git(operation="status")
Git(operation="diff", staged=True)
Git(operation="add", paths=["src/main.py", "tests/test_main.py"])
Git(operation="commit", message="Fix null pointer in user lookup")
Git(operation="push", branch="feature/fix-auth")
Git(operation="log", n=10)
Git(operation="branch", action="create", name="feature/new-thing")
```

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `operation` | str | yes | One of the supported operations (see below) |
| `reason` | str | yes | Injected by framework |
| *(operation-specific)* | — | — | See per-operation table |

### Supported Operations

| Operation | Parameters | Destructive | Description |
|---|---|---|---|
| `status` | — | no | Working tree status |
| `diff` | `staged: bool = False`, `paths: list = None` | no | Unstaged or staged diff |
| `log` | `n: int = 20`, `branch: str = None` | no | Recent commits |
| `add` | `paths: list` | no | Stage specific files |
| `add_all` | — | no | Stage all changes (`git add -A`) |
| `commit` | `message: str` | no | Commit staged changes |
| `push` | `branch: str = None`, `remote: str = "origin"` | no | Push to remote |
| `pull` | `branch: str = None`, `remote: str = "origin"` | no | Pull from remote |
| `branch` | `action: str`, `name: str = None` | no/yes | list / create / delete |
| `checkout` | `target: str` | no | Switch branch or restore file |
| `reset` | `mode: str = "soft"`, `ref: str = "HEAD~1"` | **yes** | Reset commits |
| `stash` | `action: str = "push"`, `message: str = None` | no | push / pop / list |

### Destructive operation guard

`reset` (hard/mixed) and `branch delete` are destructive. They require `allow_destructive=True` to be passed at the `Agent` constructor level — not per-call. This makes the agent's capability set explicit at construction time.

```python
# This agent can't accidentally reset --hard
agent = Agent(name="coder", tools=[Git, ...])

# This agent is explicitly authorized for destructive git ops
agent = Agent(name="release-manager", tools=[Git.bind(allow_destructive=True), ...])
```

If a destructive operation is called without `allow_destructive=True`, `Git` returns an error string explaining the restriction. The agent can surface this to the user via `HumanInput` if needed.

### Working directory

`Git` runs in `cwd` by default. In CLI mode, this is the sandboxed working directory. The `repo_path` parameter can override it — but only within the sandbox root.

### Output format

- `status` → same format as `git status --short` with a summary line
- `diff` → raw unified diff, capped at 20,000 characters with truncation notice
- `log` → one line per commit: `{hash} {date} {author} {message}`
- `commit` → `"Committed: {hash} — {message}"`
- `push` → stdout from git, trimmed
- All errors → git's stderr, returned as a `ToolResult` error string

---

## What's out of scope

- **Merge / rebase** — too complex and too destructive for v1. `Bash` remains the escape hatch.
- **Submodules** — out of scope.
- **Credential management** — assumes the environment is already authenticated (SSH key or credential helper). Git's auth errors surface as normal error strings.
- **GitAgent agentic variant** — not needed; `Git` operations are fast and atomic. No sub-agent needed.

---

## File Layout

```
nori/tools/
    git.py     # Git tool
```

---

## Open Questions

None. Ready to implement.
