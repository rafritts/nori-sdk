# SPEC-09 — Scratchpad: Shared Agent Context

## Problem

Discovered in SPEC-08 (incident response exercise): when an orchestrator agent
accumulates rich context across many turns — investigator reports, synthesis,
approved fix plans — that context does not flow to sub-agents called as tools.
Each sub-agent starts cold. The PostMortemAgent, given only a thin task string,
hallucinated an entirely fictional incident report.

The root cause is structural: Nori's agent-as-tool pattern passes only the task
string across the sub-agent boundary. Everything in the parent's LLM context
stays there.

A `Scratchpad` is the fix: a shared workspace that orchestration agents own and
that sub-agents can read from and write to.

---

## Design

### Propagation enum

Added to `nori/enums.py`:

```python
class Propagation(Enum):
    ALWAYS        = "always"        # sub-agents always inherit the scratchpad
    NEVER         = "never"         # scratchpad is private to this agent
    DISCRETIONARY = "discretionary" # agent decides at runtime
```

`None` passed by the user is treated as `DISCRETIONARY` at runtime.

### ScratchpadUsage enum

Added to `nori/enums.py`:

```python
class ScratchpadUsage(Enum):
    REQUIRED  = "required"  # agents must use the scratchpad; treat it as mandatory
    SELECTIVE = "selective" # write only genuinely critical information; do not clutter
```

Nori injects language into every agent's system prompt based on the usage level:

- **`REQUIRED`**: "The scratchpad is your primary coordination mechanism. Write
  your findings to it and read from it before producing output. Treat it as
  required, not optional."
- **`SELECTIVE`**: "Only write to the scratchpad if the information is critical
  for other agents. Do not write verbose summaries, intermediate steps, or
  anything a downstream agent could derive itself."

### Scratchpad class

```python
class Scratchpad:
    def __init__(
        self,
        schema: type[BaseModel] | None = None,
        propagate: Propagation | None = None,
        usage: ScratchpadUsage | None = None,
        audit: bool = True,
        audit_path: str | None = None,
    ): ...
```

- `schema=None` → untyped mode: free-form key-value store (`dict[str, str]`)
- `schema=MyModel` → typed mode: the scratchpad IS an instance of `MyModel`;
  all reads and writes are validated against it
- `propagate=None` → defaults to `ALWAYS` — sub-agents inherit the scratchpad automatically
- `usage=None` → defaults to `REQUIRED` — agents are instructed to treat the scratchpad as mandatory
- `audit=True` → logs the final scratchpad state to `nori.scratchpad` at `INFO` level when the owning agent exits
- `audit_path="path/to/scratchpad.json"` → additionally writes the final state as JSON to this path

Only top-level orchestration agents may create and attach a scratchpad.
Sub-agents access an inherited scratchpad via tools — they do not create their own.

### Audit output

```python
pad = Scratchpad(
    schema=IncidentFindings,
    propagate=Propagation.ALWAYS,
    usage=ScratchpadUsage.REQUIRED,
    audit_path="exercises/incident_response/scratchpad_audit.json",
)
```

The file written is:
```json
{
  "agent": "IncidentCoordinator",
  "scratchpad": {
    "log_timeline": "...",
    "database_findings": "...",
    ...
  }
}
```

The dump happens in the `finally` block of `Agent.run()` regardless of whether
the run succeeded or raised. This means you get the audit even on timeout or
agent error — useful for post-incident forensics.

---

## Two modes

### Untyped (key-value)

```python
pad = Scratchpad(propagate=Propagation.ALWAYS, usage=ScratchpadUsage.REQUIRED)
```

Agents write arbitrary string values under string keys. Flexible; no contract
enforced between agents.

### Typed (Pydantic schema)

```python
class IncidentFindings(BaseModel):
    log_timeline: str = ""
    database_bugs: str = ""
    cache_findings: str = ""
    code_audit: str = ""
    approved_fixes: list[str] = []

pad = Scratchpad(
    schema=IncidentFindings,
    propagate=Propagation.ALWAYS,
    usage=ScratchpadUsage.REQUIRED,
)
```

- Writes are validated against the schema; invalid field names or values return
  an error to the agent
- The schema (field names, types, current values) is serialized and injected into
  every agent's system prompt automatically — agents know exactly what to write
  and what has already been written
- Enforces the contract between agents; no agent can write garbage the next one
  cannot parse

---

## Tool surface

Three tools in `nori/tools/scratchpad.py`:

### ScratchpadWrite

```python
ScratchpadWrite(key: str, value: str) -> str
```

**Untyped**: writes `value` under `key`. Returns confirmation.

**Typed**: `key` must be a valid field on the schema. `value` is validated before
writing. Returns a clear error if the field does not exist or the value is invalid.

### ScratchpadRead

```python
ScratchpadRead(key: str) -> str
```

**Untyped**: returns the value stored under `key`, or `"key not found"`.

**Typed**: returns the current value of the named field.

### ScratchpadPropagate

```python
ScratchpadPropagate() -> str
```

Enables propagation at runtime. Only injected when `propagate=DISCRETIONARY` (or
`None`). Once called, sub-agents spawned afterward inherit the scratchpad. One-way
for now — `ScratchpadUnpropagate` deferred until a real use case emerges.

---

## Propagation mechanics

Implemented via a `ContextVar[Scratchpad | None]` in `nori/scratchpad.py`,
following the same pattern as `_agent_name_var` in `nori/server.py`.

In `Agent.run()`:

| `propagate` value | Behavior |
|---|---|
| `ALWAYS` | ContextVar set to this scratchpad before run starts |
| `NEVER` | ContextVar not set; parent's scratchpad (if any) is shadowed with `None` |
| `DISCRETIONARY` | ContextVar not set initially; set when agent calls `ScratchpadPropagate()` |

Sub-agents check the ContextVar in their tool implementations. If it is `None`,
`ScratchpadRead` and `ScratchpadWrite` return `"No scratchpad available in this
context."`.

---

## Tool injection

- **Attached scratchpad** (orchestrator): `ScratchpadRead`, `ScratchpadWrite` are
  injected automatically. `ScratchpadPropagate` is injected only when
  `propagate=DISCRETIONARY`.

- **Inherited scratchpad** (sub-agent): the sub-agent must include
  `ScratchpadRead` and/or `ScratchpadWrite` in its `tools=` list explicitly.
  Sub-agent participation is opt-in — auto-injection at run time would be
  invisible and surprising.

---

## Files

| File | Change |
|---|---|
| `nori/enums.py` | Add `Propagation` and `ScratchpadUsage` enums |
| `nori/scratchpad.py` | New: `Scratchpad` class + `_scratchpad_var` ContextVar |
| `nori/tools/scratchpad.py` | New: `ScratchpadRead`, `ScratchpadWrite`, `ScratchpadPropagate` |
| `nori/tools/__init__.py` | Export the three scratchpad tools |
| `nori/agent.py` | Accept `scratchpad=` param; auto-inject tools; set ContextVar in `run()`; inject usage language into system prompt |
| `exercises/incident_response/run.py` | Update to use Scratchpad — fix the PostMortemAgent hallucination |
| `tests/unit/test_scratchpad.py` | New: unit tests |

---

## Usage example (incident exercise fixed)

```python
from nori import Agent
from nori.scratchpad import Scratchpad
from nori.enums import Propagation, ScratchpadUsage
from nori.tools.scratchpad import ScratchpadRead, ScratchpadWrite

class IncidentFindings(BaseModel):
    log_timeline: str = ""
    database_bugs: str = ""
    cache_findings: str = ""
    code_audit: str = ""
    health_probe: str = ""
    approved_fixes: list[str] = []

pad = Scratchpad(
    schema=IncidentFindings,
    propagate=Propagation.ALWAYS,
    usage=ScratchpadUsage.REQUIRED,
)

log_analyst = Agent(
    name="LogAnalystAgent",
    tools=[Bash, FileSearch, ScratchpadWrite],
    system_prompt="... Write your findings to the scratchpad under 'log_timeline'.",
)

postmortem_agent = Agent(
    name="PostMortemAgent",
    tools=[Bash, ScratchpadRead],
    system_prompt="... Read all fields from the scratchpad before writing the post-mortem.",
)

coordinator = Agent(
    name="IncidentCoordinator",
    scratchpad=pad,
    tools=[log_analyst, ..., postmortem_agent],
)
```

---

## What this does not solve

- **Conversation history sharing**: sub-agents still start with a blank message
  history. The scratchpad carries conclusions, not reasoning.
- **Cross-run persistence**: scratchpad lifetime is the orchestrator's `run()`
  call. Not a substitute for a database.
- **Runtime unpropagate**: propagation is one-way for now.
