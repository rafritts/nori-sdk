# SPEC-07 — Embedded Server & HumanInput Tool

## Motivation

Agentic workflows often need to pause and ask a human before proceeding — to approve a destructive action, resolve ambiguity, or make a judgment call the agent can't. This is human-in-the-loop (HITL).

Nori supports HITL via a built-in `HumanInput` tool. The tool is transport-agnostic: it creates an `asyncio.Future` and waits. Something resolves that future — either a CLI `input()` call (default) or an HTTP POST to Nori's optional embedded server.

The embedded server is optional, starts as a background task in the same event loop as the agent, and is designed to grow into a general control plane for monitoring, audit, and agent management.

---

## Configuration

```python
import nori

# Simplest — enable server on default port
nori.configure(server=True)

# Custom port / host
nori.configure(server={"port": 8765, "host": "0.0.0.0"})

# Disable (default)
nori.configure(server=False)
```

`AgentDefaults` gains a `server` field:

```python
@dataclass
class AgentDefaults:
    ...
    server: bool | dict = False
```

A helper resolves the field to a `ServerConfig`:

```python
@dataclass
class ServerConfig:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 7731
```

`nori.configure(server=True)` → `ServerConfig(enabled=True)` (defaults apply).  
`nori.configure(server={"port": 9000})` → `ServerConfig(enabled=True, port=9000)`.

---

## Server Lifecycle

The server starts **lazily** — on the first call to `agent.run()` when `server.enabled` is True, not at `configure()` time. This avoids startup cost when no agents run.

The server runs as an `asyncio.Task` in the same event loop as the agents. It uses `uvicorn.Server.serve()` (not `uvicorn.run()`), which accepts an existing loop.

Startup is idempotent — multiple `agent.run()` calls share one server instance for the process lifetime. The server shuts down when the process exits.

```
process start
    │
    ├─ nori.configure(server=True)     # no server yet
    │
    ├─ agent.run()                     # first run: starts server as background task
    │       └─ asyncio.create_task(server.serve())
    │
    └─ agent.run()                     # subsequent runs: server already running, reuse
```

---

## HumanInput Tool

### Agent usage

```python
from nori.tools import HumanInput

agent = Agent(
    name="Reviewer",
    model=model,
    tools=[HumanInput()],
)
```

### What the agent sees

The tool is described to the model as:

> Pause execution and ask the human operator a question. Use this when you need approval, clarification, or a judgment call before proceeding. Provide a clear, specific question. Use `options` when the answer should be one of a fixed set of choices.

Schema:
```json
{
  "question": "string (required) — the question to ask the human",
  "options":  "list[str] (optional) — suggested responses; advisory, not enforced"
}
```

### Transport selection

```
HumanInput.call(question, options)
    │
    ├─ server enabled?
    │       YES → register pending request → wait on asyncio.Future
    │                    (resolved by POST /hitl/{id}/respond)
    │
    └─       NO  → asyncio.to_thread(input, formatted_prompt)
                        (blocks in thread pool, doesn't stall event loop)
```

### CLI output format (no server)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Agent: Reviewer
  Question: Should I delete all rows older than 90 days?
  Options: [yes] [no] [ask me later]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Your response: _
```

Options are printed as hints; any text is accepted.

### Return value

The human's response string is returned as the tool result. The agent decides what to do with it — Nori imposes no semantics on "yes" vs. "no".

---

## Pending Request Store

A module-level dict maps request IDs to open futures:

```python
# nori/server.py (or nori/_hitl.py)
_pending: dict[str, asyncio.Future] = {}
```

`HumanInput` workflow:
1. Generate `request_id = uuid4().hex`
2. Create `future = asyncio.get_event_loop().create_future()`
3. Store `_pending[request_id] = future`
4. Emit a log line: `[nori] waiting for human input — POST /hitl/{request_id}/respond`
5. `await future`
6. Remove `_pending[request_id]`
7. Return `future.result()`

---

## HTTP API

All endpoints are on the embedded server. Default base: `http://127.0.0.1:7731`.

### `GET /hitl/pending`

Returns all open HITL requests the human hasn't answered yet.

```json
[
  {
    "id": "a3f9b2c1",
    "agent": "Reviewer",
    "question": "Should I delete all rows older than 90 days?",
    "options": ["yes", "no"],
    "created_at": "2026-05-09T14:23:01Z"
  }
]
```

### `POST /hitl/{id}/respond`

Resolves a pending request.

```json
{ "response": "yes" }
```

Returns `200 OK` on success, `404` if the ID is unknown or already resolved.

### `GET /health`

Liveness check. Returns `{"status": "ok"}`. Useful for orchestrators.

---

## Future Extensions (out of scope for this spec)

These endpoints are **not** built in this iteration but are the reason the server exists:

| Endpoint | Purpose |
|---|---|
| `GET /agents` | List running and completed agent runs |
| `GET /runs/{id}` | Full run trace (turns, tool calls, token counts) |
| `POST /runs/{id}/cancel` | Interrupt a running agent |
| `GET /metrics` | Token usage, cost, latency |

The server architecture should not preclude these. Route registration should be additive.

---

## Known Gaps

- **No authentication.** The server binds to `127.0.0.1` by default, which limits exposure, but any local process can resolve HITL requests. Auth is deferred.
- **No timeout on HITL requests.** If the human never responds, the agent waits indefinitely. A `timeout` parameter on `HumanInput` can be added later.
- **HITL state is journaled with the run.** See SPEC-20. A kill mid-wait keeps the request id, and an answer that was committed is replayed on resume. The embedded server's in-memory futures still die with the process; resume re-registers them.

---

## Files to Create / Modify

| File | Change |
|---|---|
| `nori/server.py` | New — FastAPI app, server lifecycle, pending request store |
| `nori/tools/human_input.py` | New — `HumanInput` tool |
| `nori/tools/__init__.py` | Export `HumanInput` |
| `nori/config.py` | Add `server` field to `AgentDefaults`, `ServerConfig` dataclass |
| `nori/agent.py` | Start server on first `run()` if configured |
| `nori/__init__.py` | No change needed (server config goes through `configure()`) |
| `pyproject.toml` | Add `fastapi` and `uvicorn` as optional dep group `server` |
| `demos/hitl_demo.py` | New — demo showing CLI and server modes |
| `tests/unit/test_hitl.py` | New — unit tests for pending store, tool logic, CLI fallback |
| `tests/integration/test_server.py` | New — httpx tests against live server |
