# Observability

## Narration

Narration fires around tool calls with the tool name and the agent's stated reason. It's the simplest way to see what an agent is doing in real time without waiting for the run to finish.

```python
agent.narration = True
```

Output goes to stdout by default:

```
MyAgent[What is today's date?]
MyAgent → Bash[checking current directory]
MyAgent → Bash[1.24s]
MyAgent: 3 turns | 2,410 tokens | $0.0061 | 4.2s
```

### Custom handler

Replace the default handler with your own callback:

```python
agent.on_narration = lambda msg: my_logger.info(msg)
```

### Multi-agent disambiguation

When running multiple agents concurrently, use `narrator_prefix` to tell their output apart:

```python
infra_agent.narrator_prefix = "[infra] "
app_agent.narrator_prefix   = "[app]   "
```

Optional flags: `narration_call_id` (default `True` — tags parallel calls), `narration_trace_id` (default `False`), `narration_summary` (default `True` — end-of-run cost/token line).

User-facing mid-run prose (including `update_for_user` status) goes through `on_assistant_content` rather than free-form tool-turn content.

See [`narration_demo.py`](https://github.com/rafritts/nori-sdk/blob/master/demos/narration_demo.py) for all three scenarios including concurrent agents with prefixes.

---

## Audit log

The audit log is a structured JSON-lines stream with full B3 tracing. Every tool call gets a `trace_id`, `span_id`, `parent_span_id`, and `call_id`. Parallel tool calls are correlated automatically.

```python
from nori.audit import AuditLogger

agent.auditor = AuditLogger("logs/my_agent.audit.log")

result = await agent.run("...")

agent.auditor.close()
```

Each line in the audit file is a JSON object. Field names match the event type — for example a tool call looks like:

```json
{
  "time": "2025-01-15T10:23:45Z",
  "event": "tool_call",
  "agent": "MyAgent",
  "name": "Bash",
  "args": {"command": "df -h", "reason": "checking disk usage"},
  "trace_id": "abc123",
  "span_id": "def456",
  "parent_span_id": "ghi789",
  "call_id": "a1b2"
}
```

Events include `agent_start`, `agent_end`, `tool_call`, `tool_result`, `tool_error`, and `compaction`.

The audit log and standard Python logging are independent. Configure `nori` loggers as you would any other logger:

```python
import logging

logging.getLogger("nori").setLevel(logging.DEBUG)
logging.getLogger("nori").addHandler(your_handler)
```

### Control tower

For a remote stream, configure a control tower WebSocket sink:

```python
nori.configure(control_tower="wss://tower.example.com", project="my-app")
```

See [Security](security.md#observability-carries-raw-data) before pointing this at an untrusted collector.

See [`observability_demo.py`](https://github.com/rafritts/nori-sdk/blob/master/demos/observability_demo.py) for a side-by-side comparison of the standard log and the audit stream.

---

## Cost tracking

After any run, `agent.cost` holds the total spend in USD (preferring provider-reported billed cost when available, otherwise the static price table):

```python
result = await agent.run("...")
print(f"Cost: ${agent.cost:.4f}")
print(f"Turns: {agent.turn_count}")
print(f"Tokens: {agent.token_counts}")
print(f"Elapsed: {agent.elapsed:.1f}s")
print(f"Tool calls: {len(agent.tool_calls)}")
```

`agent.token_counts` is a dict with `prompt`, `completion`, `reasoning`, `cached`, and `total`. `agent.tool_calls` is a list of records for every tool call made during the run. CLI-backed providers report `$0` cost.

---

## Context fill and autocompaction

Nori monitors context window usage throughout a run (based on the last completion's prompt token count vs. the model context window):

- At **70% fill**, a warning is injected into the conversation prompting the agent to wrap up or call `Compact`.
- At **85% fill**, the history is compacted automatically into the running summary.
- The agent can also call the `Compact` tool voluntarily if you register it (`from nori.tools.compact import Compact` and pass it in `tools=`).

Enable rolling context summaries to keep long multi-turn conversations lean:

```python
agent = Agent(
    name="MyAgent",
    system_prompt="...",
    running_context_summary=True,
)
```

After each call to `agent.run()`, the history is compressed into a rolling summary. The next turn starts lean.

See [`context_demo.py`](https://github.com/rafritts/nori-sdk/blob/master/demos/context_demo.py) for both running summaries and forced autocompaction.
