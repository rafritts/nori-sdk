# Observability

## Narration

Narration fires before each tool call with the tool name and the agent's stated reason. It's the simplest way to see what an agent is doing in real time without waiting for the run to finish.

```python
agent.narration = True
```

Output goes to stdout by default:

```
[MyAgent] → bash  "checking current directory"
[MyAgent] → file_read  "reading the config file"
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

Each line in the audit file is a JSON object:

```json
{
  "event": "tool_call",
  "tool": "bash",
  "trace_id": "abc123",
  "span_id": "def456",
  "parent_span_id": "ghi789",
  "call_id": "call_001",
  "reason": "checking disk usage",
  "timestamp": "2025-01-15T10:23:45Z"
}
```

The audit log and standard Python logging are independent. Configure `nori` loggers as you would any other logger:

```python
import logging

logging.getLogger("nori").setLevel(logging.DEBUG)
logging.getLogger("nori").addHandler(your_handler)
```

See [`observability_demo.py`](https://github.com/rafritts/nori-sdk/blob/master/demos/observability_demo.py) for a side-by-side comparison of the standard log and the audit stream.

---

## Cost tracking

After any run, `agent.cost` holds the total spend in USD:

```python
result = await agent.run("...")
print(f"Cost: ${agent.cost:.4f}")
print(f"Turns: {agent.turn_count}")
print(f"Tool calls: {len(agent.tool_calls)}")
```

`agent.tool_calls` is a list of records for every tool call made during the run.

---

## Context fill and autocompaction

Nori monitors context window usage throughout a run:

- At **70% fill**, a warning is injected into the conversation prompting the agent to wrap up or call `Compact`.
- At **85% fill**, the history is compacted automatically.
- The agent can also call the `Compact` tool voluntarily at any time.

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
