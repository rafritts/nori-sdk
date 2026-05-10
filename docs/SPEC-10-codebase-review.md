# SPEC-10: Codebase Review

**Date:** 2026-05-10  
**Scope:** All files under `nori/`, `tests/`, `demos/`, `exercises/`  
**Tools used:** `ruff` (78 issues), `mypy` (29 errors), `radon` (CC + MI), manual review  

---

## What this is not

This review intentionally omits:

- **Mypy false positives on valid patterns.** The `_UNSET` sentinel, `functools.wraps` losing custom attributes, `**kwargs` unpacking through typed APIs, and conditional module imports all produce mypy errors but are idiomatic Python. Fixing them requires Protocols, `cast()`, `TYPE_CHECKING` guards, or a typed sentinel class — machinery that adds more noise than it removes. Mypy stays in the dev dependencies as a sanity check, not a zero-tolerance gate.
- **Thread-safety of module globals.** `config._defaults` and `server._pending` are not thread-safe. This is an asyncio library running in a single event loop. Adding locks now solves a hypothetical problem while adding real complexity.
- **Magic constants that are stable implementation details.** `recent[-20:]` in anti_spin, `recent[-10:]` in context summary, `asyncio.sleep(0.15)` for uvicorn startup — these are fine inline. Making them named constants adds indirection for values that will never be user-configured.
- **Missing `| None` on list defaults.** `tools: list = None` instead of `list | None = None` throughout. Python handles this correctly at runtime; mypy flags it. Not worth the churn.
- **`tools/__init__.py` only exporting 2 of 13 tools.** Users import directly from `nori.tools.bash`, etc. No one is doing `from nori.tools import *`. Low practical impact.

---

## Real Issues — Fix These

### 1. `PermissionError` shadows Python's built-in
**File:** `nori/exceptions.py`  
**Severity:** High

```python
class PermissionError(Exception):
    pass
```

`PermissionError` is a built-in. In any scope that does `from nori.exceptions import PermissionError`, the OS-level built-in is shadowed. A `try/except PermissionError` block that intends to catch "file access denied" will also catch nori's tool permission denials, and vice versa. Silent, hard to debug.

**Fix:** Rename to `ToolPermissionError`.

---

### 2. `context_fill()` compares characters to tokens
**File:** `nori/agent.py`  
**Severity:** High — the compaction mechanism is functionally broken

```python
def _context_fill(self) -> float:
    total = sum(_content_len(m.get("content")) for m in self._history)
    return total / self.max_context_chars  # max_context_chars = model.context_window (tokens)
```

`_content_len` returns `len(str(content))` — characters. `max_context_chars` holds `model.context_window` — tokens. English text averages ~4 characters per token, so the ratio is off by 4x. The 85% compaction threshold is only reached when history is ~340% of the actual token budget, which is never. The 70% warning is equally broken.

The actual token count is already available: `self._prompt_tokens` accumulates from every API response.

**Fix:**
```python
def _context_fill(self) -> float:
    if not self.max_context_chars:
        return 0.0
    return self._prompt_tokens / self.max_context_chars
```

The field name `max_context_chars` is now misleading — rename to `_context_window` or similar when making this change.

---

### 3. `AuditLogger` leaks its file handle
**File:** `nori/audit.py`  
**Severity:** Medium

```python
self._file = open(path, "a", buffering=1)
```

There is no `__enter__`/`__exit__`. The demos call `close()` manually, but as a library class there's no guarantee. If an exception occurs before `close()`, the handle leaks.

**Fix:** Add `__enter__`/`__exit__` so it works as a context manager. Two methods, low overhead.

```python
def __enter__(self):
    return self

def __exit__(self, *_):
    self.close()
```

---

### 4. `Bash` tool silently drops exit codes
**File:** `nori/tools/bash.py`  
**Severity:** Medium — causes real agent reliability problems

```python
proc = subprocess.run(command, shell=True, capture_output=True, text=True)
output = proc.stdout
if proc.stderr:
    output += f"\n[stderr]\n{proc.stderr}"
return ToolResult(result=output)
```

A failed command (exit code 1, no stderr) is indistinguishable from a successful one with no output. The LLM cannot tell if the command failed. This has caused agents to proceed confidently after silent failures.

**Fix:** Prefix with exit code when non-zero:
```python
if proc.returncode != 0:
    output = f"[exit code: {proc.returncode}]\n" + output
```

---

### 5. `FileEdit` raises unhandled `FileNotFoundError`
**File:** `nori/tools/file_edit.py`  
**Severity:** Medium

```python
file = Path(path)
text = file.read_text()  # FileNotFoundError propagates up and terminates the run
```

Every other tool error is returned as a `ToolResult` with an error message. A missing file should be too.

**Fix:**
```python
try:
    text = file.read_text()
except FileNotFoundError:
    return ToolResult(result=f"File not found: {path}")
```

---

### 6. `WebClient` has no network error handling
**File:** `nori/tools/web_client.py`  
**Severity:** Medium — same pattern as FileEdit

`httpx.ConnectError`, `httpx.TimeoutException`, `httpx.ReadError` all propagate as uncaught exceptions. Should return `ToolResult(result=f"[network error] {e}")`.

---

### 7. `Agent.__call__` silently drops most constructor params
**File:** `nori/agent.py`  
**Severity:** Medium

When an `Agent` is used as a tool, the sub-agent is spawned without `scratchpad`, `permissions`, `checkpoint`, `self_modify`, `context_files`, `summarize_tool_output`, or `running_context_summary`. If any of these were configured, they are silently lost with no error or warning.

**Fix:** Forward all params. The sub-agent should be a faithful copy of the parent's configuration.

---

### 8. MCP tools never receive the `summary` field
**File:** `nori/agent.py` — `_inject_reason_into_schema`  
**Severity:** Medium

MCP tool schemas get `reason` injected, but not `summary`. Every MCP tool call shows `[elapsed]` with no summary in narration, defeating the summary feature for MCP tools entirely.

**Fix:** Mirror the `reason` injection for `summary` in `_inject_reason_into_schema`.

---

### 9. `result` variable redefined with a different type in `_invoke_tool`
**File:** `nori/agent.py`  
**Severity:** Low — clarity issue, not a bug

```python
result = await fn(**args)            # ToolResult
...
result: dict = {"role": "tool", ...} # dict
```

Same name, two incompatible types, in the same function. Confusing to read and mypy flags it correctly as `no-redef`.

**Fix:** Rename the final dict to `tool_msg`.

---

### 10. `Scratchpad`, `Propagation`, `ScratchpadUsage` not in `nori.__init__`
**File:** `nori/__init__.py`  
**Severity:** Low — usability

Everything else (`Agent`, `Model`, `Permissions`, `Checkpoint`, etc.) is importable from `nori` directly. Scratchpad types require `from nori.scratchpad import ...`. Inconsistent.

**Fix:** Add to `__init__.py` and `__all__`.

---

### 11. `FileSearchAgent.model = None` is a fragile side-channel
**File:** `nori/tools/file_search_agent.py`  
**Severity:** Low

```python
FileSearchAgent.model = None  # written after decoration, read inside the function
```

The framework writes to `FileSearchAgent.model` during `Agent.__init__` tool resolution. This is the only tool that uses this pattern. If the module is imported before the model is configured, `model` is `None` and the sub-agent call fails. Every other agent-backed tool reads from `config.get_defaults()` inside the function body.

**Fix:** Remove the `.model` attribute. Inside `FileSearchAgent`, read `config.get_defaults().tool_models` directly, falling back to the global default model. The framework already does this lookup in `Agent.__init__` — don't replicate it.

---

### 12. Ruff: 78 linting issues, 65 auto-fixable
**Severity:** Low — `uv run ruff check --fix .`

The fixable set is noise-free: unused imports in tests and demos, split multi-imports, remove bare f-strings. The main manual decision: `import config` in every demo is an intentional side-effect import. Add `# noqa: F401` to each, or restructure demos to call `config.configure()` explicitly (cleaner but more churn).

The 3 instances of `l` as a variable name (ambiguous with `1`) in test files and `file_search.py` should be renamed to `line`.

---

### 13. `ScratchpadPropagate` returns raw `str`, not `ToolResult`
**File:** `nori/scratchpad.py`  
**Severity:** Low — works due to `_invoke_tool` fallback, but inconsistent

Every other tool returns `ToolResult(result=...)`. The fallback `str(result)` in `_invoke_tool` handles it, but if that fallback is ever removed this silently breaks.

**Fix:** One-line change.

---

### 14. `enums.py` re-exports `Provider` from `providers.py`
**File:** `nori/enums.py`  
**Severity:** Low

```python
from nori.providers import Provider  # re-exported for backward compat
```

`Provider` is an enum, but it lives in `providers.py` (alongside pricing and HTTP client factories) because it needs to read env vars. Re-exporting it from `enums.py` creates `enums → providers` coupling that isn't obvious. If backward compat is the goal, `__init__.py` is the right place.

**Fix:** Remove from `enums.py`. It's already importable from `nori` directly via `__init__.py`.

---

---

## Part 2: Complexity and SRP Analysis

**Tool:** `radon cc` (cyclomatic complexity) and `radon mi` (maintainability index)

### The finding in one sentence

Every file in the codebase is healthy except `agent.py`, which scores MI=0 (radon's floor) and contains four methods with C/D-grade complexity.

### Cyclomatic complexity scores (B or worse)

| Score | Grade | Method | What it does |
|-------|-------|--------|-------------|
| 23 | D | `Agent.__init__` | Constructor |
| 20 | C | `Agent._run_loop` | Main agent loop |
| 15 | C | `Agent._invoke_tool` | Single tool dispatch |
| 15 | C | `Agent.run` | Public entry point |
| 12 | C | `Model.__post_init__` | Model validation |
| 10 | B | `Agent._clean_history` | History cleanup |
| 9  | B | `Agent._apply_strips` | Image strip cleanup |
| 9  | B | `Agent._build_messages` | Message construction |

Everything else in the codebase is A-grade (1–5). The problem is entirely concentrated in `agent.py`.

### Why `agent.py` scores MI=0

MI combines lines of code, cyclomatic complexity, and comment density. `agent.py` is 665 lines. With four C/D methods and minimal inline comments, radon floors the score. MI=0 doesn't mean the code is broken — it means a new contributor reading it has a lot to hold in their head at once.

### SRP analysis

`Agent` has these distinct responsibility clusters currently mixed together:

**Narration** — 11 attributes and methods dedicated to printing output:  
`narration`, `narrator_prefix`, `narration_call_id`, `narration_trace_id`, `narration_summary`, `on_narration`, `_default_narrator`, `_narrate`, `_narrate_elapsed`, `_narrate_result`, `_narrate_summary`

**Context management** — fill calculation, compaction, and the 70%/85% warning logic:  
`max_context_chars`, `_compact_warning_injected`, `_context_fill`, `_compact`, and inline branching inside `_run_loop`

**Tool dispatch** — permission checking, argument extraction, timeout, error handling, result processing, strip-after-read:  
`_invoke_tool`, `_execute_tools`, `_permissions`

**Core loop** — turn counting, API calls, history management, anti-spin checkpoint:  
`_run_loop`, `_complete`, `_build_messages`, `_clean_history`, `_message_to_dict`, `_apply_strips`

**Bookkeeping** — token counts, cost, elapsed, tool call log, auditing, tracing:  
`_prompt_tokens`, `_completion_tokens`, `_tool_calls_log`, `_run_start`, `_elapsed`, `auditor`, `_trace_id`, `_span_id`

### What's actually worth fixing

**Don't refactor into separate classes.** All five clusters share `self` state heavily. A `Narrator` class would need to hold a reference back to the agent to access `_trace_id`, `narrator_prefix`, etc. A `ContextManager` class would need `_history`, `_client`, `_model`. Extracting into classes means either passing a lot of state or creating circular references — the cure is worse than the disease.

**Do extract private methods from the hot methods.** This is the correct pragmatic lever. The three high-CC methods (`_run_loop`, `_invoke_tool`, `__init__`) each contain coherent sub-blocks that can become named private methods, dropping CC without moving any state.

---

### 15. `_run_loop` complexity — extract sub-blocks
**File:** `nori/agent.py`  
**CC before:** 20 (C grade)  
**Severity:** Medium

`_run_loop` does five distinct things inline: turn limit enforcement, context fill + compaction, compact warning injection, anti-spin checkpoint evaluation, and loop exit. The fill/compaction/warning block alone is 15 lines with 3 branches — enough to be a private method.

**Fix:** Extract two methods:
```python
async def _handle_context_pressure(self, fill: float) -> None:
    """Compact or warn based on fill level."""
    if fill >= 0.85:
        await self._compact(fill=fill)
    elif fill >= 0.70 and not self._compact_warning_injected:
        self._history.append({"role": "user", "content": _COMPACT_WARNING, "_marker": _COMPACT_MARKER})
        self._compact_warning_injected = True
        msg = f"{self.narrator_prefix}{self.name}[Context warning ({fill:.0%} full)]"
        narration_logger.debug(msg)
        if self.narration:
            self.on_narration(msg)

async def _evaluate_checkpoint(self) -> None:
    """Run anti-spin check and optionally compact."""
    recent = self._history[-self._checkpoint.every * 4:]
    is_spin, summary = await evaluate_checkpoint(recent, self._checkpoint.scrutiny, self._client, self.model)
    if is_spin:
        raise AntiSpinTerminated(f"Anti-spin triggered at turn {self._turn_count}. Summary: {summary}")
    if self._checkpoint.compact:
        self._history = inject_summary(self._history, summary)
```

Estimated CC after: ~10 (B grade). Drops the loop to its essential structure: call API, check fill, check for tools, dispatch or return.

---

### 16. `_invoke_tool` complexity — extract audit/narration bookend
**File:** `nori/agent.py`  
**CC before:** 15 (C grade)  
**Severity:** Low-Medium

`_invoke_tool` has a clear structure: setup → narrate/audit start → execute → narrate/audit end → build return. The narration and audit calls at both ends are identical in shape. The Compact special case at the very top (`if tc.function.name == "Compact"`) is also a code smell — one tool with a completely different dispatch path that bypasses permissions, timeouts, and logging entirely.

**Fix:** Move the Compact early-return into a named check, and extract the audit bookend:
```python
async def _invoke_tool(self, tc, is_parallel: bool = False) -> dict:
    if self._is_compact_call(tc):
        return await self._handle_compact(tc)
    ...
```

Extracting `_is_compact_call` and `_handle_compact` removes the biggest irregular branch and makes the main dispatch path clean.

Estimated CC after: ~9 (B grade).

---

### 17. `Agent.__init__` complexity — extract tool registration
**File:** `nori/agent.py`  
**CC before:** 23 (D grade)  
**Severity:** Low-Medium

Most of the CC in `__init__` comes from two sources: (1) `_UNSET` sentinel resolution (3 branches), and (2) tool registration — iterating tools, injecting models, registering scratchpad tools, registering self-modify tools. The latter is a coherent block that doesn't need to be inline.

**Fix:** Extract into `_register_tools(tools, scratchpad, self_modify)`:
```python
def _register_tools(self, tools: list, scratchpad, self_modify, defaults) -> None:
    self._tools = {self._tool_name(t): t for t in (tools or [])}
    for t in self._tools.values():
        if hasattr(t, "model") and t.model is None:
            t.model = defaults.tool_models.get(t) or defaults.tool_models.get(type(t)) or self._model
    if self_modify is not None:
        self._register_self_modify_tools(self_modify)
    if scratchpad is not None:
        read_tool, write_tool = _make_owner_tools(scratchpad)
        self._tools[self._tool_name(read_tool)] = read_tool
        self._tools[self._tool_name(write_tool)] = write_tool
        if scratchpad.propagate == Propagation.DISCRETIONARY:
            propagate_tool = _make_propagate_tool(scratchpad)
            self._tools[self._tool_name(propagate_tool)] = propagate_tool
```

Estimated CC after: ~15 (C grade, moving toward B). Still complex due to `_UNSET` resolution, but the tool registration block is out.

---

## Summary

| # | Severity | What | File |
|---|----------|------|------|
| 1 | High | `PermissionError` shadows built-in | exceptions.py |
| 2 | High | `context_fill()` chars vs tokens — compaction never fires | agent.py |
| 3 | Medium | `AuditLogger` missing context manager | audit.py |
| 4 | Medium | `Bash` drops exit codes | tools/bash.py |
| 5 | Medium | `FileEdit` unhandled `FileNotFoundError` | tools/file_edit.py |
| 6 | Medium | `WebClient` no network error handling | tools/web_client.py |
| 7 | Medium | `Agent.__call__` drops scratchpad/permissions/checkpoint | agent.py |
| 8 | Medium | MCP tools missing `summary` injection | agent.py |
| 9 | Low | `result` redef with different type in `_invoke_tool` | agent.py |
| 10 | Low | Scratchpad types missing from `nori.__init__` | \_\_init\_\_.py |
| 11 | Low | `FileSearchAgent.model` side-channel mutation | tools/file_search_agent.py |
| 12 | Low | 78 ruff issues (65 auto-fixable) | various |
| 13 | Low | `ScratchpadPropagate` returns raw string | scratchpad.py |
| 14 | Low | `Provider` re-exported from `enums.py` | enums.py |
| 15 | Medium | `_run_loop` CC=20 — extract `_handle_context_pressure` + `_evaluate_checkpoint` | agent.py |
| 16 | Low-Med | `_invoke_tool` CC=15 — extract Compact handling + fix irregular dispatch | agent.py |
| 17 | Low-Med | `Agent.__init__` CC=23 — extract `_register_tools` | agent.py |
