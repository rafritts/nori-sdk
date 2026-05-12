# SPEC-02: Audit & Request Tracing

Full distributed request tracing for Nori agents, modeled on Spring Cloud Sleuth/Zipkin (B3 propagation). Sensible defaults, opt-in/opt-out where needed.

---

## Motivation

Parallel tool calls produce interleaved narration output with no way to correlate a "Started" line with its "Result" line. Orchestrator/sub-agent hierarchies produce audit logs with no way to reconstruct which sub-calls belong to which parent run. This spec fixes both while keeping narration clean for humans and audit rich for machines.

---

## Concepts

| Concept | Type | Scope | Purpose |
|---|---|---|---|
| `trace_id` | Full UUID4 | Per top-level `agent.run()` | Immutable. Inherited by all sub-agents and tool spans. The thing you search by in Splunk/Datadog. |
| `span_id` | 8-char hex | Per `agent.run()` or tool invocation | Links parent→child within a trace. Short because it's always scoped to a known `trace_id`. |
| `parent_span_id` | 8-char hex or None | Per span | Points to the span that created this one. `null` for the root. |
| `call_id` | 4-char hex | Per tool invocation | `span_id[:4]`. Display alias only — for human-readable terminal correlation. |

### Span Tree Example

```
trace_id=406ff458-840f-4a30-bee1-25e5d71fa1f6
│
├─ span_id=aa01b3f2  parent=null            Orchestrator.run()
│   ├─ span_id=bb02c4e1  parent=aa01b3f2    tool_call: Researcher
│   │   └─ span_id=cc03d5f0  parent=bb02c4e1   Researcher.run()
│   │       └─ span_id=dd04e6a9  parent=cc03d5f0  tool_call: web_lookup
│   └─ span_id=ee05f7b8  parent=aa01b3f2    tool_call: Writer
│       └─ span_id=ff06a8c7  parent=ee05f7b8   Writer.run()
│           └─ span_id=gg07b9d6  parent=ff06a8c7  tool_call: format_as_markdown
```

`trace_id` flows unchanged through every level. Each `agent.run()` and each tool invocation mints a new `span_id`. `call_id` is `span_id[:4]`.

---

## Narration

Narration is a UX feature — human-facing, terminal output. Trace IDs do not belong here by default.

### Default behavior
```
fetch_price[User wants price of AAPL]
```

Single tool call: no call_id, no trace ID — clean.

### Parallel turn (auto call_id)
When a turn has multiple tool calls, `call_id` is automatically injected:
```
fetch_price-agh7[User wants price of AAPL] - Started
get_weather-b3x1[User wants weather in Austin] - Started
fetch_price-agh7[Result: AAPL: $213.49]
get_weather-b3x1[Result: Austin: Sunny, 75°F]
```

Single calls stay clean. Parallel calls get correlation automatically — no config needed.

### Opt-in / opt-out

| Setting | Type | Default | Effect |
|---|---|---|---|
| `narration_call_id` | `bool` | `True` | Auto-inject `call_id` on parallel turns |
| `narration_trace_id` | `bool` | `False` | Opt-in: always show `trace_id` in narration |

With `narration_trace_id=True`:
```
fetch_price-agh7[406ff458-840f-4a30-bee1-25e5d71fa1f6][Started: User wants price of AAPL]
fetch_price-agh7[406ff458-840f-4a30-bee1-25e5d71fa1f6][Result: AAPL: $213.49]
```

Result lines are always flat — no `└─` decoration, no multiline. Newlines in result content replaced with ` | `.

---

## Audit Stream

Audit is machine-facing. Full B3 tracing on every event, always — when an auditor is attached. No per-field toggles.

### agent_start
```json
{
  "time": "2026-05-09T01:14:12Z",
  "event": "agent_start",
  "trace_id": "406ff458-840f-4a30-bee1-25e5d71fa1f6",
  "span_id": "aa01b3f2",
  "parent_span_id": null,
  "agent": "Orchestrator",
  "prompt": "Write a comparison of Python, Rust, and Go."
}
```

### tool_call
```json
{
  "time": "2026-05-09T01:14:16Z",
  "event": "tool_call",
  "trace_id": "406ff458-840f-4a30-bee1-25e5d71fa1f6",
  "span_id": "bb02c4e1",
  "parent_span_id": "aa01b3f2",
  "call_id": "bb02",
  "agent": "Orchestrator",
  "name": "fetch_price",
  "args": {"ticker": "AAPL", "reason": "User wants current price of AAPL stock"}
}
```

### tool_result
```json
{
  "time": "2026-05-09T01:14:16Z",
  "event": "tool_result",
  "trace_id": "406ff458-840f-4a30-bee1-25e5d71fa1f6",
  "span_id": "bb02c4e1",
  "parent_span_id": "aa01b3f2",
  "call_id": "bb02",
  "agent": "Orchestrator",
  "name": "fetch_price",
  "result": "AAPL: $213.49"
}
```

### tool_error
```json
{
  "time": "2026-05-09T01:14:16Z",
  "event": "tool_error",
  "trace_id": "406ff458-840f-4a30-bee1-25e5d71fa1f6",
  "span_id": "bb02c4e1",
  "parent_span_id": "aa01b3f2",
  "call_id": "bb02",
  "agent": "Orchestrator",
  "name": "fetch_price",
  "error": "Connection refused"
}
```

### agent_end
```json
{
  "time": "2026-05-09T01:14:20Z",
  "event": "agent_end",
  "trace_id": "406ff458-840f-4a30-bee1-25e5d71fa1f6",
  "span_id": "aa01b3f2",
  "parent_span_id": null,
  "agent": "Orchestrator",
  "result": "AAPL is currently $213.49.",
  "turns": 2,
  "cost": 0.0072
}
```

---

## Propagation Rules

| Scenario | trace_id | span_id | parent_span_id |
|---|---|---|---|
| Top-level `agent.run()` | New UUID4 | New 8-char hex | `null` |
| Sub-agent `agent.run()` (called as tool) | Inherited | New 8-char hex | Calling agent's `span_id` |
| Tool invocation | Inherited | New 8-char hex | Enclosing `agent.run()` `span_id` |

---

## API Changes

### `Agent` — new attributes

| Attribute | Type | Default | Description |
|---|---|---|---|
| `narration_call_id` | `bool` | `True` | Auto-inject `call_id` on parallel turns |
| `narration_trace_id` | `bool` | `False` | Always show `trace_id` in narration |
| `trace_id` | `str \| None` | `None` | Read-only. Set at start of `run()`. |
| `span_id` | `str \| None` | `None` | Read-only. Set at start of `run()`. |
| `parent_span_id` | `str \| None` | `None` | Set by orchestrator before calling sub-agent. |

### `_narrate(tool_name, reason, call_id, is_parallel)`
- If `is_parallel` and `narration_call_id`: inject `call_id`
- If `narration_trace_id`: inject `trace_id`
- Emits Started line

### `on_tool_result(name, result, call_id, trace_id)`
- Gains `call_id` and `trace_id`
- Default handler emits Result line using same rules as narration

### `AuditLogger` — updated signatures

| Method | Signature |
|---|---|
| `agent_start` | `(agent, prompt, trace_id, span_id, parent_span_id)` |
| `tool_call` | `(agent, name, args, trace_id, span_id, parent_span_id, call_id)` |
| `tool_result` | `(agent, name, result, trace_id, span_id, parent_span_id, call_id)` |
| `tool_error` | `(agent, name, error, trace_id, span_id, parent_span_id, call_id)` |
| `agent_end` | `(agent, result, turns, cost, trace_id, span_id, parent_span_id)` |

---

## Implementation Steps

### Step 1 — ID generation
- Generate `trace_id` (UUID4) at top of `agent.run()` — inherit if provided by caller
- Generate `span_id` (8-char hex from `uuid4().hex[:8]`) at top of `agent.run()`
- Generate tool `span_id` per `_invoke_tool()`, derive `call_id` as `span_id[:4]`
- Expose `trace_id`, `span_id` as read-only properties

### Step 2 — Narration format update
- Add `narration_call_id = True` and `narration_trace_id = False` to `Agent.__init__`
- Update `_narrate()` to accept `call_id` and `is_parallel`
- Update `_execute_tools()` to pass `is_parallel = len(tool_calls) > 1`
- Emit Started/Result lines per narration rules above

### Step 3 — `on_tool_result` update
- New signature: `(name, result, call_id, trace_id)`
- Default handler applies same call_id/trace_id rules as narration
- Update all demo lambdas

### Step 4 — Audit stream update
- Add `trace_id`, `span_id`, `parent_span_id`, `call_id` to all `AuditLogger` methods
- Update all call sites in `agent.py`

### Step 5 — Trace propagation to sub-agents
- In `Agent.__call__()`, pass `self._trace_id` and `self._span_id` to sub-agent
- Sub-agent sets `trace_id = inherited`, `parent_span_id = caller span_id`, mints new `span_id`

### Step 6 — Unit tests
- `test_trace_id_generated_at_run` — UUID4 format
- `test_span_id_is_8_char_hex`
- `test_call_id_is_first_4_chars_of_span_id`
- `test_trace_id_inherited_by_sub_agent`
- `test_parent_span_id_set_on_sub_agent`
- `test_call_id_absent_on_single_tool_call` — no call_id when only one tool called
- `test_call_id_present_on_parallel_tool_calls`
- `test_narration_trace_id_opt_in`
- `test_narration_call_id_opt_out`
- `test_on_tool_result_receives_call_id_and_trace_id`
- `test_audit_events_carry_full_b3_fields`
- `test_tool_span_parent_is_agent_span_id`

### Step 7 — Update demos
- Remove custom `on_tool_result` lambdas — default output is now correct
- Update `observability_demo.py` to showcase narration vs audit formats
- Update `agent_as_tool_demo.py` to show trace propagation across agents

---

## Out of Scope (Future)

- OpenTelemetry exporter
- Turn-level span IDs (each LLM completion as its own span)
- Latency/duration tracking per span
- W3C `traceparent` header propagation for HTTP-based MCP tools
- Sampling / trace filtering
