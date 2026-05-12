# SPEC-13: Deferred Tools

## Goal

Allow tools to be registered with an agent without loading their full schemas into the context window. This reduces token cost when an agent has a large tool set but only uses a subset per run.

## Problem

Every tool attached to an agent contributes its full JSON schema to every LLM call. An agent with 10 tools pays that schema cost even if it only ever calls 2 of them. For a CLI agent with a broad tool set, this is wasteful on every single turn.

## Design

### New Agent Parameter: `deferred_tools`

```python
agent = Agent(
    name="cli",
    tools=[Bash],                          # full schema — always visible
    deferred_tools=[WebSearch, FileEdit, BrowserAgent, ...],  # registered but hidden
    show_tool_stubs=False,                 # default: deferred tools are invisible
)
```

### Behavior by `show_tool_stubs`

**`show_tool_stubs=False` (default)**

Deferred tools are registered with the agent but completely invisible to the LLM. The agent works with only its `tools` schemas. If the task requires a deferred tool, it won't know to ask for it. Use this when the attached tools are sufficient and you don't want distraction.

**`show_tool_stubs=True`**

Each deferred tool appears as a compact stub in the tool list — name and one-line description only, no parameters. The agent can see what's available and request one via a special `ExpandTool` meta-tool. Once expanded, the full schema is injected for the next turn and the agent calls it normally with full parameters.

### The Expansion Mechanic (Option B)

When `show_tool_stubs=True`, the agent has access to an auto-injected `ExpandTool`:

```
ExpandTool(tool_name: str) -> str
```

The agent calls `ExpandTool("WebSearch")` when it decides it needs it. The framework:

1. Removes the stub for that tool from the tool list
2. Adds the full schema to the active tool list
3. Returns a confirmation: `"WebSearch is now available. Call it directly."`

On the next turn, the agent calls `WebSearch(...)` with full parameter control. Expanded tools stay expanded for the remainder of the run.

### Tool Groups (Option C)

Users can also declare named groups for explicit tier control:

```python
agent = Agent(
    name="cli",
    tools=[Bash],
    deferred_tools={
        "web": [WebSearch, WebClient, ApiClient],
        "files": [FileEdit, FileSearch],
        "browser": [BrowserAgent, BrowserClient],
    },
    show_tool_stubs=True,
)
```

When groups are used, `ExpandTool` accepts either a tool name or a group name:

```
ExpandTool("web")  →  expands WebSearch, WebClient, ApiClient all at once
```

Plain lists (Option B) and dicts (Option C) are both valid. The framework handles both.

## Token Impact

| Mode | What the LLM sees |
|---|---|
| `tools=[A, B, C]` | Full schemas for A, B, C |
| `tools=[A], deferred_tools=[B, C]` | Full schema for A only |
| `tools=[A], deferred_tools=[B, C], show_tool_stubs=True` | Full schema for A + stubs for B, C + ExpandTool schema |
| After `ExpandTool("B")` | Full schemas for A, B + stub for C + ExpandTool schema |

## Implementation

### 1. `Agent.__init__`

- Accept `deferred_tools: list | dict | None`
- Store deferred tools in `self._deferred_tools: dict[str, type]` (name → tool class)
- If `show_tool_stubs=True`, inject `ExpandTool` into the active tool list and generate stubs

### 2. Stub Generation

A stub is a trimmed tool schema: only `name` and `description`, no `parameters`. Generated from the existing tool schema at init time, not at call time.

### 3. `ExpandTool` Meta-Tool

Auto-injected when `show_tool_stubs=True`. Not user-facing — never appears in `Agent.tools`. Mutates the agent's active tool list by moving a tool from deferred → active.

### 4. `_register_tools` Refactor

The existing `_register_tools` method will need to support the split between active (full schema) and deferred (stub or hidden) tool sets.

## What's Out of Scope

- Lazy tool *unloading* — once expanded, a tool stays expanded for the run
- Stub customization — stubs are always auto-generated from the tool's existing description
- Per-turn tool visibility changes beyond the expand mechanic

## Open Questions

None. Ready to implement.
