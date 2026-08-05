# Anti-Spin

Agents can get stuck. A tool returns ambiguous results, the model decides to try again, and suddenly you're 30 turns deep going nowhere. Anti-spin detects this and stops it.

Every N turns, Nori evaluates the agent's recent history with an isolated LLM call. The evaluator summarizes recent progress and returns `SPIN` or `PROGRESS`. On `SPIN`, `AntiSpinTerminated` is raised.

---

## Basic setup

```python
from nori import Agent, Checkpoint, CheckpointScrutiny

agent = Agent(
    name="MyAgent",
    system_prompt="...",
    tools=[...],
    checkpoint=Checkpoint(every=3, scrutiny=CheckpointScrutiny.MODERATE),
)
```

`every=3` means a checkpoint runs every 3 turns. `scrutiny` controls how aggressively the evaluator judges progress.

---

## `Checkpoint` fields

| Field | Type | Default | Description |
|---|---|---|---|
| `every` | `int` | required | Run a checkpoint every N turns (must be &gt; 0) |
| `scrutiny` | `CheckpointScrutiny` | `MODERATE` | How aggressive the evaluator is |
| `compact` | `bool` | `False` | If true and not spinning, inject the evaluator's summary into history |

---

## Scrutiny levels

| Level | Behavior |
|---|---|
| `STRICT` | Terminates at the first sign of repetition or stalling |
| `MODERATE` | Allows some retries; terminates on clear loops |
| `LENIENT` | Only terminates on obvious, extended spinning |

Use `STRICT` for tasks with a well-defined completion condition. Use `LENIENT` for exploratory tasks where the agent legitimately needs multiple attempts.

---

## Handling `AntiSpinTerminated`

```python
from nori.exceptions import AntiSpinTerminated

try:
    result = await agent.run("Investigate anomaly XJ-7.")
except AntiSpinTerminated as e:
    print(f"Agent stuck after {agent.turn_count} turns: {e}")
```

---

## `max_turns` vs. anti-spin

`max_turns` is a hard ceiling — the run stops regardless of progress (default is `10` unless configured). Anti-spin is smarter: it evaluates whether the agent is actually moving forward and stops early when it isn't.

Use both together for tight control:

```python
agent = Agent(
    name="MyAgent",
    tools=[...],
    max_turns=20,
    checkpoint=Checkpoint(every=4, scrutiny=CheckpointScrutiny.STRICT),
)
```

Set `max_turns=None` to remove the ceiling and rely on anti-spin alone for termination.

---

See [`anti_spin_demo.py`](https://github.com/rafritts/nori-sdk/blob/master/demos/anti_spin_demo.py) for both scenarios: a healthy agent that passes every checkpoint, and a spinning agent that gets terminated.
