# Anti-Spin

Agents can get stuck. A tool returns ambiguous results, the model decides to try again, and suddenly you're 30 turns deep going nowhere. Anti-spin detects this and stops it.

Every N turns, Nori asks [Jev](https://docs.typesafe.ai/introduction) one yes/no question about the recent history: is the agent spinning? Jev returns the probability that the answer is yes. Scrutiny is the probability at which Nori stops the run. On a stop, `AntiSpinTerminated` is raised.

The check calls `jev-1.13.0` at TypeSafe and needs `TYPESAFE_API_KEY` (environment variable or a `.env` file). Input is billed at $0.042 per million tokens, and that cost is added to `agent.cost`. A failed call stops the run with that error. It is not treated as progress, and it is not treated as spin.

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

`every=3` means a checkpoint runs every 3 turns. `scrutiny` is how sure Jev has to be before Nori stops the run.

---

## `Checkpoint` fields

| Field | Type | Default | Description |
|---|---|---|---|
| `every` | `int` | required | Run a checkpoint every N turns (must be &gt; 0) |
| `scrutiny` | `CheckpointScrutiny` | `MODERATE` | Probability cutoff for stopping |
| `compact` | `bool` | `False` | If true and not spinning, inject the checkpoint note into history |

---

## Scrutiny levels

The question is the same at every level: are these turns repeating work without moving the task forward? A retry that tries something new, or that uses new information from the last result, is progress. Scrutiny only changes the cutoff.

| Level | Stop when P(spin) is at least |
|---|---|
| `STRICT` | 0.50 |
| `MODERATE` | 0.75 |
| `LENIENT` | 0.90 |

Use `STRICT` for tasks with a well-defined completion condition. Use `LENIENT` for exploratory tasks where the agent legitimately needs multiple attempts.

Jev does not write a summary. With `compact=True`, the note injected into history is the probability, the cutoff, and a short trace of the recent turns (who spoke, which tools ran, and a clip of each result). Image bytes are not sent.

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
