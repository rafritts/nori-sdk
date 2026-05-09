# SPEC-05: Application Configuration

## Overview

Users should be able to configure agent defaults once — globally — rather than repeating the same kwargs on every `Agent(...)` call. This mirrors the Spring Boot `@Configuration` pattern: a single place in the user's application wires up models, timeouts, and per-tool model overrides. Nori provides the hook; the user provides the config.

## API

### `nori.configure(**kwargs)`

Sets global defaults. Any field not passed to `Agent(...)` directly falls back to these values.

```python
import nori
from nori import Model, Provider
from nori.tools.bash import Bash
from nori.tools.file_search import FileSearch

nori.configure(
    model=Model(id="claude-opus-4-7", provider=Provider.ANTHROPIC),
    tool_timeout=30.0,
    run_timeout=300.0,
    max_turns=20,
    narration=True,
    tool_models={
        Bash: Model(id="claude-sonnet-4-6", provider=Provider.ANTHROPIC),
        FileSearch: Model(id="claude-haiku-4-5", provider=Provider.ANTHROPIC),
    },
)
```

Calling `nori.configure()` again merges into the existing defaults (later calls win field-by-field). `tool_models` dicts are merged the same way.

### `nori.reset()`

Clears all global defaults back to `None`. Primarily for test isolation.

```python
nori.reset()
```

### Configurable fields

| Field | Type | Notes |
|---|---|---|
| `model` | `Model` | Default model for all agents |
| `tool_timeout` | `float \| None` | Per-tool call timeout (seconds) |
| `run_timeout` | `float \| None` | Full run timeout (seconds) |
| `max_turns` | `int` | Maximum agentic turns |
| `narration` | `bool` | Print turn-by-turn narration |
| `tool_models` | `dict[type, Model]` | Per-tool model overrides |

`system_prompt` and `tools` are intentionally excluded — they are too agent-specific to be meaningful as global defaults.

## Tool model resolution

For tools that internally invoke a model (sub-agents), the resolved model is determined at `Agent.__init__` time:

1. **Tool instance has `model` explicitly set** → use it
2. **Tool class appears in `tool_models`** (direct pass or global config) → use that model
3. **Main agent's model** → last resort

The agent applies this resolution when registering tools, so every tool that exposes a `model` attribute gets it set before the first run.

### Tool protocol

Any tool class that uses an internal model should expose a `model` attribute (defaulting to `None`) so the agent can inject the resolved model:

```python
class FileSearch:
    model: Model | None = None
    ...
```

Tools decorated with `@tool` (plain functions) never use a model — resolution is skipped for them.

## Agent resolution order

For every field on `Agent`, resolution is:

1. Value explicitly passed to `Agent(...)` → **wins**
2. Global default from `nori.configure()` → fallback
3. Hardcoded `Agent` default (e.g. `max_turns=10`) → last resort

This means `nori.configure()` sits between user-explicit and framework-default. Passing `None` explicitly to `Agent(...)` is treated as "not set" and falls through to the global default. If the user genuinely wants to disable a global default for one agent, they pass a sentinel or a zero value appropriate to the field (e.g. `run_timeout=0` is not meaningful — use a dedicated `disable` pattern if needed; for now document that explicit `None` falls through).

## Implementation plan

### 1. `nori/config.py` (new)

```python
@dataclass
class AgentDefaults:
    model: Model | None = None
    tool_timeout: float | None = None
    run_timeout: float | None = None
    max_turns: int | None = None
    narration: bool | None = None
    tool_models: dict[type, Model] = field(default_factory=dict)

_defaults = AgentDefaults()

def configure(**kwargs) -> None:
    tool_models = kwargs.pop("tool_models", None)
    for k, v in kwargs.items():
        setattr(_defaults, k, v)
    if tool_models:
        _defaults.tool_models.update(tool_models)

def reset() -> None:
    global _defaults
    _defaults = AgentDefaults()

def get_defaults() -> AgentDefaults:
    return _defaults
```

### 2. `nori/__init__.py`

Export `configure` and `reset` at the top level:

```python
from nori.config import configure, reset
```

### 3. `Agent.__init__`

After setting all explicit kwargs, fall back to global defaults for any field that is still `None` (or sentinel):

```python
from nori.config import get_defaults

_d = get_defaults()
self.model = model or _d.model
self.tool_timeout = tool_timeout if tool_timeout is not None else _d.tool_timeout
self.run_timeout = run_timeout if run_timeout is not None else _d.run_timeout
self.max_turns = max_turns if max_turns is not None else (_d.max_turns or 10)
self.narration = narration if narration is not None else (_d.narration or False)
```

### 4. Tool model injection (in `Agent.__init__`)

After resolving the agent's own model, walk the tool list and inject models:

```python
_tool_models = {**get_defaults().tool_models, **tool_models_kwarg}

for t in self.tools:
    if hasattr(t, "model") and t.model is None:
        resolved = _tool_models.get(type(t)) or self.model
        t.model = resolved
```

### 5. Tests

- `test_configure_sets_agent_defaults` — agent constructed with no kwargs uses global defaults
- `test_agent_kwargs_win_over_configure` — explicit agent kwargs override global defaults
- `test_tool_models_in_configure` — tool gets correct model from global config
- `test_tool_explicit_model_wins` — tool with model set directly ignores global tool_models
- `test_reset_clears_defaults` — after `nori.reset()`, agents get framework defaults again
- `test_configure_merges_tool_models` — two `nori.configure()` calls merge tool_models dicts

## Open questions

- Should `nori.configure()` be a context manager (`with nori.configure(...)`) for test isolation, or is `nori.reset()` sufficient? Lean toward `reset()` for now — simpler.
- If a user calls `nori.configure()` from multiple modules (common in large apps), the merge behavior needs to be clearly documented. Last-call-wins on scalar fields, dict-merge on `tool_models`.
