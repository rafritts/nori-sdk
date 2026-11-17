# SPEC-20 — Durable runs

## Motivation

An agent run, including a HITL wait, lived entirely in process memory. Killing the process dropped the conversation, the in-flight tool call, and any human answer that had not yet been applied. The run has to survive being shut off at an arbitrary moment.

## Design

Every run is snapshotted to a SQLite file (WAL, `synchronous=FULL`) before each model call and around each tool call. A commit is the durability boundary. A kill loses only the step that had not committed.

Default path: `$NORI_STATE_PATH` or `~/.nori/runs.db`. `nori.configure(durable=False)` disables it. `durable="/path"` or `durable={"path": "/path"}` sets the file. Durability is on by default.

```python
result = await agent.run(prompt)             # new id, logged at info
result = await agent.run(run_id=id)          # resume, or return the stored result
result = await agent.run(prompt, run_id=id)  # start that id, or resume it
nori.list_runs(status="running")
```

Resume rebuilds the loop cursor onto a newly constructed agent: history, turn flags, token counters, system prompt, model id, max turns, scratchpad, and the active tool set (expanded deferred tools, removed tools). The caller passes the same tools and MCP servers. MCP is reconnected, then the registry is matched to the snapshot.

### What is retried

| Last committed point | On resume |
|---|---|
| About to call the model | Call the model again |
| Assistant message committed, tools not started | Run the tools |
| Tool marked started, result not committed | Run that tool again |
| Tool result committed | Do not run it again |
| Run status `done` | Return the stored result |
| Run status `error` | Re-raise. Do not retry |

Tools are at-least-once. A side effect that landed and then the process died before the result commit will happen again. `run_timeout` and cancellation leave the run resumable. A tool exception, `MaxTurnsExceeded`, and `AntiSpinTerminated` mark the run `error`.

### HITL

`HumanInput` stores `(run_id, tool_call_id) → request_id` before it waits. `POST /hitl/{id}/respond` commits the answer before it wakes the agent. On resume:

- If the answer is committed, the tool returns it and does not ask again.
- If it is not, the same request id is registered and the wait continues.

`GET /hitl/pending` merges live waits with journal rows that have no answer, so a question is visible after restart even before `run(run_id=...)` is called. Responding before resume commits the answer; the resumed tool picks it up.

### Nested runs

A tool call that starts another agent run allocates a stable child id, `{parent_run_id}/{tool_call_id}` and then `#n` for further children of that call. Re-executing the tool allocates the same ids in the same order. A child that already finished returns its stored result.

## Known limits

- Not exactly-once. Idempotent tool arguments are the caller's job when a repeat would be harmful.
- Two processes must not resume the same run id at once. Last commit wins.
- The resume agent must be built with the same tools. The journal cannot serialize function objects.
- `run_timeout` starts over on resume. It does not accumulate across processes.
