# SPEC-02: Audit & Request Tracing

Full distributed request tracing for Nori agents, modeled loosely on Spring Cloud Sleuth/Zipkin. Every tool invocation gets a short human-readable ID for terminal output and a UUID for machine-readable correlation. Every audit event carries the full run ID.

---

## Motivation

Parallel tool calls produce interleaved narration output with no way to correlate a "Started" line with its "Result" line. Longer-running orchestrator/sub-agent hierarchies produce audit logs with no way to reconstruct which sub-calls belong to which parent run. This spec fixes both.

---

## Concepts

| Concept | Type | Scope | Purpose |
|---|---|---|---|
| `run_id` | UUID4 | Per `agent.run()` call | Globally unique identifier for one agent run. Shared by all events in that run. |
| `call_id` | 4-char hex | Per tool invocation | Short human-scannable ID. Correlates Started/Result lines in terminal output. |
| `parent_run_id` | UUID4 or None | Per sub-agent invocation | The `run_id` of the calling agent. Enables span hierarchy reconstruction. |

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
- `call_id` is a 4-char lowercase hex string generated per tool invocation
- `run_id` is the UUID for the current `agent.run()` call
- Result is printed on a single flat line — no `└─` decoration, no multiline formatting
- Newlines in result content are replaced with ` | ` for display

---

## Audit Stream Format

All existing audit events gain `run_id` and, where applicable, `call_id` and `parent_run_id`.

### agent_start
```json
{
  "time": "2026-05-09T01:14:12Z",
  "event": "agent_start",
  "run_id": "406ff458-840f-4a30-bee1-25e5d71fa1f6",
  "parent_run_id": null,
  "agent": "ObservabilityDemo",
  "prompt": "What OS am I on?"
}
```

### tool_call
```json
{
  "time": "2026-05-09T01:14:16Z",
  "event": "tool_call",
  "run_id": "406ff458-840f-4a30-bee1-25e5d71fa1f6",
  "call_id": "agh7",
  "agent": "ObservabilityDemo",
  "name": "fetch_price",
  "args": {"ticker": "AAPL", "reason": "User wants current price of AAPL stock"}
}
```

### tool_result
```json
{
  "time": "2026-05-09T01:14:16Z",
  "event": "tool_result",
  "run_id": "406ff458-840f-4a30-bee1-25e5d71fa1f6",
  "call_id": "agh7",
  "agent": "ObservabilityDemo",
  "name": "fetch_price",
  "result": "AAPL: $213.49"
}
```

### tool_error
```json
{
  "time": "2026-05-09T01:14:16Z",
  "event": "tool_error",
  "run_id": "406ff458-840f-4a30-bee1-25e5d71fa1f6",
  "call_id": "agh7",
  "agent": "ObservabilityDemo",
  "name": "fetch_price",
  "error": "Connection refused"
}
```

### agent_end
```json
{
  "time": "2026-05-09T01:14:20Z",
  "event": "agent_end",
  "run_id": "406ff458-840f-4a30-bee1-25e5d71fa1f6",
  "parent_run_id": null,
  "agent": "ObservabilityDemo",
  "result": "AAPL is currently $213.49.",
  "turns": 2,
  "cost": 0.0072
}
```

---

## Sub-Agent Tracing

When an Agent is called as a tool by an orchestrator, the sub-agent's `run_id` is a new UUID but its `parent_run_id` is set to the orchestrator's `run_id`. This creates a reconstructable span tree.

```
Orchestrator  run_id=406ff458  parent_run_id=null
  └─ Researcher  run_id=9c3a1d22  parent_run_id=406ff458
  └─ Writer      run_id=b7f02e11  parent_run_id=406ff458
```

The orchestrator's audit log will contain `tool_call` events for `Researcher` and `Writer`. The sub-agent audit logs (if using the same `AuditLogger`) will carry `parent_run_id` linking them back.

---

## API Changes

### `Agent`

| Attribute | Type | Description |
|---|---|---|
| `run_id` | `str \| None` | UUID of the current run. Set at start of `run()`, cleared on completion. Exposed as a read-only property. |
| `parent_run_id` | `str \| None` | Set by the orchestrator before invoking a sub-agent. |

### `_narrate(tool_name, reason, call_id)`
Gains `call_id` parameter. Emits:
```
{tool_name}-{call_id}[{run_id}][Started: {reason}]
```

### `on_narration(text)`
Signature unchanged. Receives the fully formatted string.

### `on_tool_result(name, result, call_id, run_id)`
Gains `call_id` and `run_id`. Default handler emits:
```
{name}-{call_id}[{run_id}][Result: {result_single_line}]
```

### `AuditLogger`

| Method | New params |
|---|---|
| `agent_start(agent, prompt, run_id, parent_run_id)` | `run_id`, `parent_run_id` |
| `tool_call(agent, name, args, run_id, call_id)` | `run_id`, `call_id` |
| `tool_result(agent, name, result, run_id, call_id)` | `run_id`, `call_id` |
| `tool_error(agent, name, error, run_id, call_id)` | `run_id`, `call_id` |
| `agent_end(agent, result, turns, cost, run_id, parent_run_id)` | `run_id`, `parent_run_id` |

---

## Implementation Steps

### Step 1 — `run_id` and `call_id` generation
- Generate `run_id` (UUID4) at the top of `agent.run()`
- Generate `call_id` (4-char hex) at the top of `_invoke_tool()`
- Expose `run_id` as a read-only property on `Agent`

### Step 2 — Narration format update
- Update `_narrate()` to accept and embed `call_id` and `run_id`
- Update `_invoke_tool()` to pass `call_id` to `_narrate()`
- Replace default `on_narration` output with new bracket format

### Step 3 — `on_tool_result` signature update
- Add `call_id` and `run_id` to `on_tool_result` callback signature
- Update default handler to emit flat single-line result in new format
- Update all demo lambdas to match new signature

### Step 4 — Audit stream update
- Add `run_id` and `call_id` to all `AuditLogger` methods
- Add `parent_run_id` to `agent_start` and `agent_end`
- Update `_invoke_tool()` and `run()` call sites

### Step 5 — Sub-agent `parent_run_id` threading
- When `Agent.__call__()` spawns a sub-agent, pass `self._run_id` as `parent_run_id`
- Sub-agent carries it through to its own audit events

### Step 6 — Unit tests
- `test_run_id_generated_per_run` — each `run()` call produces a unique UUID
- `test_call_id_in_narration` — narration string contains 4-char call_id
- `test_run_id_in_narration` — narration string contains run_id
- `test_on_tool_result_receives_call_id` — callback receives correct call_id
- `test_audit_tool_call_has_run_id_and_call_id`
- `test_audit_agent_start_has_parent_run_id_none` — no parent by default
- `test_parent_run_id_threaded_to_sub_agent` — orchestrator's run_id appears as sub-agent's parent_run_id

### Step 7 — Update demos
- Remove custom `on_tool_result` lambdas from demos — default output is now correct
- Update `observability_demo.py` to highlight the new format side-by-side

---

## Out of Scope (Future)

- Centralized trace collector / exporter (OpenTelemetry)
- Turn-level span IDs (each LLM completion gets its own span)
- Latency tracking per tool call
- W3C `traceparent` header propagation for HTTP-based MCP tools
