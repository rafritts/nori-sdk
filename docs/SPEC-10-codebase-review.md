# SPEC-10: Codebase Review

**Date:** 2026-05-10  
**Scope:** All files under `nori/`, `tests/`, `demos/`, `exercises/`  
**Tools used:** `ruff` (78 issues), `mypy` (29 errors), manual review  

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
