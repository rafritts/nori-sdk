# SPEC-02: Audit & Request Tracing

Full distributed request tracing for Nori agents, modeled on Spring Cloud Sleuth/Zipkin (B3 propagation). Every logical request carries a single `trace_id` from top to bottom. Every unit of work — agent runs and tool invocations — is a **span** with its own `span_id` and a `parent_span_id` pointing to whoever created it.

---

## Motivation

Parallel tool calls produce interleaved narration output with no way to correlate a "Started" line with its "Result" line. Orchestrator/sub-agent hierarchies produce audit logs with no way to reconstruct which sub-calls belong to which parent run. This spec fixes both.

---

## Concepts

| Concept | Type | Scope | Purpose |
|---|---|---|---|
| `trace_id` | UUID4 | Per top-level `agent.run()` | Immutable. Inherited by all sub-agents and tool spans within one logical request. |
| `span_id` | UUID4 | Per `agent.run()` or tool invocation | Unique ID for this unit of work. |
| `parent_span_id` | UUID4 or None | Per span | Points to the span that created this one. `None` for the root span. |
| `call_id` | 4-char hex | Per tool invocation | Short human-scannable alias for `span_id`. Terminal readability only. |

### Span Tree Example

```
trace_id=406ff458
│
├─ span_id=aa01  parent=null          Orchestrator.run()
│   ├─ span_id=bb02  parent=aa01      tool_call: Researcher (as tool)
│   │   └─ span_id=cc03  parent=bb02  Researcher.run()
│   │       └─ span_id=dd04  parent=cc03  tool_call: web_lookup
│   └─ span_id=ee05  parent=aa01      tool_call: Writer (as tool)
│       └─ span_id=ff06  parent=ee05  Writer.run()
│           └─ span_id=gg07  parent=ff06  tool_call: format_as_markdown
```

`trace_id` flows unchanged through every level. Each `agent.run()` and each tool invocation mints a new `span_id`. The `parent_span_id` is the `span_id` of whoever initiated the call.

---

## Narration Format

### Current
```
fetch_price[User wants current price of AAPL stock]
  └─ AAPL: $213.49
```

### New
```
fetch_price-agh7[406ff458-840f-4a30-bee1-25e5d71fa1f6][Started: User wants current price of AAPL stock]
fetch_price-agh7[406ff458-840f-4a30-bee1-25e5d71fa1f6][Result: AAPL: $213.49]
```

Rules:
- `call_id` is a 4-char lowercase hex string — short alias for the tool span's `span_id`
- The UUID shown is `trace_id` — consistent across the whole request
- Result is a single flat line — no `└─` decoration, no multiline
- Newlines in result content are replaced with ` | ` for display

---

## Audit Stream Format

All audit events carry `trace_id`, `span_id`, and `parent_span_id`. Tool events also carry `call_id`.

### agent_start
```json
{
  "time": "2026-05-09T01:14:12Z",
  "event": "agent_start",
  "trace_id": "406ff458-840f-4a30-bee1-25e5d71fa1f6",
  "span_id": "9c3a1d22-...",
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
  "span_id": "bb02...",
  "parent_span_id": "aa01...",
  "call_id": "agh7",
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
  "span_id": "bb02...",
  "parent_span_id": "aa01...",
  "call_id": "agh7",
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
  "span_id": "bb02...",
  "parent_span_id": "aa01...",
  "call_id": "agh7",
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
  "span_id": "9c3a1d22-...",
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
| Top-level `agent.run()` | New UUID4 | New UUID4 | `null` |
| Sub-agent `agent.run()` (called as tool) | Inherited from parent | New UUID4 | Calling agent's `span_id` |
| Tool invocation | Inherited | New UUID4 | Enclosing `agent.run()` span_id |

---

## API Changes

### `Agent`

| Attribute | Type | Description |
|---|---|---|
| `trace_id` | `str \| None` | Inherited or generated at `run()`. Read-only property. |
| `span_id` | `str \| None` | Generated at start of each `run()`. Read-only property. |
| `parent_span_id` | `str \| None` | Set by orchestrator before calling sub-agent. |

### `_narrate(tool_name, reason, call_id)`
Gains `call_id`. Emits:
```
{prefix}{tool_name}-{call_id}[{trace_id}][Started: {reason}]
```

### `on_narration(text)`
Signature unchanged. Receives the fully formatted string.

### `on_tool_result(name, result, call_id, trace_id)`
Gains `call_id` and `trace_id`. Default handler emits:
```
{name}-{call_id}[{trace_id}][Result: {result_single_line}]
```

### `AuditLogger`

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
- Generate `trace_id` (UUID4) at top of `agent.run()` — inherit from caller if provided
- Generate `span_id` (UUID4) at top of `agent.run()`
- Generate tool `span_id` + derive `call_id` (first 4 hex chars of span_id) at top of `_invoke_tool()`
- Expose `trace_id`, `span_id` as read-only properties

### Step 2 — Narration format update
- Update `_narrate()` to accept `call_id`, embed `trace_id`
- Update `_invoke_tool()` to pass `call_id` to `_narrate()`
- Update default narration output to new bracket format

### Step 3 — `on_tool_result` signature update
- Add `call_id` and `trace_id` to callback signature
- Update default handler: flat single-line, new bracket format
- Update all demo lambdas

### Step 4 — Audit stream update
- Add `trace_id`, `span_id`, `parent_span_id`, `call_id` to all `AuditLogger` methods
- Update all call sites in `agent.py`

### Step 5 — Trace propagation to sub-agents
- In `Agent.__call__()`, pass `self._trace_id` and `self._span_id` to sub-agent
- Sub-agent sets `trace_id = inherited`, `parent_span_id = caller's span_id`, generates new `span_id`

### Step 6 — Unit tests
- `test_trace_id_generated_at_run` — UUID4 generated per top-level run
- `test_span_id_generated_at_run` — unique span_id per run
- `test_trace_id_inherited_by_sub_agent` — sub-agent shares trace_id with parent
- `test_parent_span_id_set_on_sub_agent` — parent's span_id is sub-agent's parent_span_id
- `test_call_id_in_narration` — 4-char call_id appears in narration string
- `test_trace_id_in_narration` — trace_id appears in narration string
- `test_on_tool_result_receives_call_id_and_trace_id`
- `test_audit_events_carry_trace_and_span_ids`
- `test_tool_span_parent_is_agent_span`

### Step 7 — Update demos
- Remove custom `on_tool_result` lambdas — default output is now correct
- Update `observability_demo.py` and `agent_as_tool_demo.py` to show trace propagation

---

## Out of Scope (Future)

- OpenTelemetry exporter
- Turn-level span IDs (each LLM completion as its own span)
- Latency/duration tracking per span
- W3C `traceparent` header propagation for HTTP-based MCP tools
- Sampling / trace filtering
