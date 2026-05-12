# SPEC-03: Agent Constructor Redesign

First-class constructs for the `Agent` constructor, and a consolidated `nori/enums.py` that eliminates magic numbers, strings, and booleans across the codebase.

---

## Motivation

The current `Agent` constructor has 19 parameters. Several are logically grouped features expressed as flat kwargs — three bools for self-modification, three for checkpointing — with no validation at construction time. Misconfiguration surfaces at runtime, not at the call site. Meanwhile, enums like `CheckpointScrutiny` and `ContextRole` are buried in implementation modules and not importable from a single obvious place.

This spec introduces four first-class constructs (`Model`, `Permissions`, `Checkpoint`, `SelfModify`), a unified `nori/enums.py`, and a slimmer, validated `Agent` constructor.

---

## `nori/enums.py`

A single file for all enums in the framework. Replaces scattered definitions in `anti_spin.py` and `context.py`.

```python
from enum import Enum, IntEnum

class ContextWindow(IntEnum):
    K24   =    24_000
    K32   =    32_000
    K128  =   128_000
    K200  =   200_000
    M1    = 1_000_000

class ContextRole(Enum):
    SYSTEM    = "system"
    USER      = "user"
    ASSISTANT = "assistant"

class CheckpointScrutiny(Enum):
    STRICT   = "strict"
    MODERATE = "moderate"
    LENIENT  = "lenient"

class SelfModify(Enum):
    CUSTODIAN = "custodian"   # read/inspect agent state only
    MODIFY    = "modify"      # edit tools and config
    MUTATION  = "mutation"    # full self-rewrite; implies MODIFY and CUSTODIAN
```

### Migration

| Current location | Moved to |
|---|---|
| `nori.anti_spin.CheckpointScrutiny` | `nori.enums.CheckpointScrutiny` |
| `nori.context.ContextRole` | `nori.enums.ContextRole` |

Internal imports in `anti_spin.py`, `context.py`, and `agent.py` are updated to import from `nori.enums`. Old import sites are updated directly — no re-exports for compatibility.

`SelfModify` is new — replaces the three `self_*` bools on `Agent`.

---

## First-Class Constructs

### `Model`

Encapsulates everything needed to talk to an LLM provider.

```python
@dataclass
class Model:
    id: str
    api_key: str | None = None
    base_url: str | None = None
    context_window: int | ContextWindow = ContextWindow.M1
```

**Validation** (raised at `Model()` construction, not at `agent.run()`):
- `id` must be a non-empty string.
- `api_key` falls back to `config.API_KEY`; if still `None` and `base_url` is also `None`, raises `ValueError` — no provider means no calls.
- `context_window` must be a positive integer.

**Usage:**
```python
local = Model(id="gemma4:31b", base_url="http://localhost:11434/v1", context_window=ContextWindow.K24)
cloud = Model(id="grok-4.3", api_key=os.environ["XAI_API_KEY"], context_window=ContextWindow.M1)
```

Users define models once and reuse them. No `ModelID` enum — model names churn too fast.

---

### `Permissions`

Encapsulates the allow/deny lists for tool gating.

```python
@dataclass
class Permissions:
    allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)
```

**Validation:**
- Names appearing in both `allow` and `deny` raise `ValueError` at construction.

**Usage:**
```python
Permissions(allow=["Bash", "FileRead"])
Permissions(deny=["Bash"])
```

Replaces the flat `allow=` and `deny=` kwargs on `Agent`. `PermissionGuard` remains an internal implementation detail.

---

### `Checkpoint`

Encapsulates checkpoint configuration.

```python
@dataclass
class Checkpoint:
    every: int
    scrutiny: CheckpointScrutiny = CheckpointScrutiny.MODERATE
    compact: bool = False
```

**Validation:**
- `every` must be a positive integer.

**Usage:**
```python
Checkpoint(every=5)
Checkpoint(every=3, scrutiny=CheckpointScrutiny.STRICT, compact=True)
```

Replaces the flat `checkpoint=`, `checkpoint_scrutiny=`, and `checkpoint_compact=` kwargs. `Agent(checkpoint=None)` disables checkpointing (default).

---

### `SelfModify`

Replaces three boolean flags with a single enum value. Levels are hierarchical: `MUTATION` implies `MODIFY` and `CUSTODIAN`; `MODIFY` implies `CUSTODIAN`.

```python
# Defined in nori/enums.py — no separate dataclass needed.
class SelfModify(Enum):
    CUSTODIAN = "custodian"
    MODIFY    = "modify"
    MUTATION  = "mutation"
```

**Usage:**
```python
Agent(..., self_modify=SelfModify.MUTATION)
Agent(..., self_modify=None)  # default — no self-modification
```

`_register_self_modify_tools()` derives which tools to register from the level. `CUSTODIAN` registers read-only tools; `MODIFY` adds edit tools; `MUTATION` adds rewrite tools.

---

## Updated `Agent` Constructor

```python
def __init__(
    self,
    name: str,
    model: Model,
    system_prompt: str = "",
    tools: list = None,
    max_turns: int | None = 10,
    description: str = "",
    context_files: list[ContextFile] = None,
    permissions: Permissions = None,
    checkpoint: Checkpoint | None = None,
    self_modify: SelfModify | None = None,
    summarize_tool_output: bool = False,
    running_context_summary: bool = False,
):
```

Down from 19 parameters to 12. `model` becomes required and typed. `api_key` and `base_url` move into `Model`. `allow`/`deny` move into `Permissions`. The three checkpoint kwargs become one. The three self-modify bools become one.

**Agent-level validation:**
- `name` must be a non-empty string.
- `max_turns` must be a positive integer or `None`.

---

## `nori/__init__.py` Exports

```python
from nori import Agent, Model, Permissions, Checkpoint
from nori.enums import ContextWindow, SelfModify, CheckpointScrutiny, ContextRole
```

---

## Implementation Steps

### Step 1 — `nori/enums.py`
- Create the file with `ContextWindow`, `ContextRole`, `CheckpointScrutiny`, `SelfModify`.
- Update `nori/anti_spin.py` and `nori/context.py` to import from `nori.enums`.
- Update `nori/agent.py` imports.
- Update `nori/__init__.py` exports.

### Step 2 — `Model`
- Define `Model` dataclass in `nori/model.py` with validation in `__post_init__`.
- Update `Agent.__init__` to accept `model: Model` instead of flat `model`, `api_key`, `base_url`.
- Update internal references (`self._api_key`, `self._base_url`, `self.model`, `self.max_context_chars`).
- Update all demos and tests.

### Step 3 — `Permissions`
- Define `Permissions` dataclass in `nori/permissions.py` with conflict validation in `__post_init__`.
- Update `Agent.__init__` to accept `permissions: Permissions = None`.
- `PermissionGuard` is constructed from `permissions.allow` / `permissions.deny` internally.
- Update demos and tests.

### Step 4 — `Checkpoint`
- Define `Checkpoint` dataclass in `nori/checkpoint.py` with validation in `__post_init__`.
- Update `Agent.__init__` to accept `checkpoint: Checkpoint | None = None`.
- Update internal references (`self._checkpoint`, `self._checkpoint_scrutiny`, `self._checkpoint_compact`).
- Update demos and tests.

### Step 5 — `SelfModify` enum
- Update `_register_self_modify_tools()` to accept a single `SelfModify | None` and derive capability flags from the level.
- Update `Agent.__init__` to accept `self_modify: SelfModify | None = None`.
- Update demos and tests.

### Step 6 — Unit tests
- `test_model_requires_id` — empty string raises `ValueError`
- `test_model_requires_provider` — no api_key and no base_url raises `ValueError`
- `test_model_invalid_context_window` — non-positive raises `ValueError`
- `test_permissions_conflict` — name in both allow and deny raises `ValueError`
- `test_checkpoint_requires_positive_every` — zero or negative raises `ValueError`
- `test_self_modify_levels` — `MUTATION` registers all tools, `CUSTODIAN` registers fewest
- `test_agent_requires_name` — empty string raises `ValueError`
- `test_context_window_enum_usable_as_int` — `ContextWindow.K24 == 24_000`

---

## Out of Scope

- `ModelID` enum — model names churn too fast; users define and reuse their own `Model` instances.
- Narration configuration object — narration is observer-pattern, correctly stays post-construction.
- Turn-level or latency configuration — future concern.
