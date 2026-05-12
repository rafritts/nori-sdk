# SPEC-14: File Tools — FileRead and FileWrite

## Motivation

Nori ships `FileEdit` (replace text in an existing file) and `FileSearch` (find files by name or content), but has no tool for reading a file's contents or creating a new file. Agents that need to read source code, config files, or data files currently fall back to `Bash` with `cat` — bypassing the sandbox, producing noisy output, and making intent invisible in the audit log. Creating new files requires `Bash` with a heredoc or redirect, which is error-prone and unsandboxed.

`FileRead` and `FileWrite` close these gaps. Together with `FileEdit` and `FileSearch`, they form a complete, sandboxed file operation suite.

---

## FileRead

Read a file and return its contents.

```python
FileRead(path="/app/config.yaml")
FileRead(path="/app/main.py", start_line=10, end_line=50)
```

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `path` | str | yes | Absolute or relative path to the file |
| `start_line` | int | no | First line to return (1-indexed, inclusive). Default: beginning of file. |
| `end_line` | int | no | Last line to return (1-indexed, inclusive). Default: end of file. |
| `reason` | str | yes | Injected by framework |

### Behavior

- Returns file contents as a string, with line numbers prepended (`  1 | content`) when `start_line` or `end_line` is specified, to help agents make precise `FileEdit` calls afterward.
- Without range parameters, returns the full file with no line number prefix.
- Enforces sandbox via `check_path()` — same as `FileEdit` and `FileSearch`.
- Returns a clear error string if the file does not exist or is not readable (no exception raised).
- Output capped at 50,000 characters. If truncated, appends: `[truncated — {n} chars omitted]`.

### Why line numbers on range reads?

When an agent reads lines 40–60 to understand a function, it will often follow up with a `FileEdit` call. Showing line numbers in the ranged output makes it easy for the agent to construct the exact `old_content` string without re-reading the whole file.

---

## FileWrite

Write content to a file, creating it (and any missing parent directories) or overwriting it entirely.

```python
FileWrite(path="/app/output/report.md", content="# Report\n...")
FileWrite(path="/tmp/scratch.py", content="print('hello')")
```

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `path` | str | yes | Absolute or relative path to write |
| `content` | str | yes | Full content to write |
| `reason` | str | yes | Injected by framework |

### Behavior

- Creates parent directories if they do not exist (`mkdir -p` semantics).
- Overwrites the file entirely if it already exists. For partial edits, use `FileEdit`.
- Enforces sandbox via `check_path()`.
- Returns a confirmation string with the path and byte count: `"Wrote 1,024 bytes to /app/output/report.md"`.

### Why not append mode?

Agents can read + rewrite if they need to append. An explicit append mode adds complexity without much value — the agent can always read the file first and include the existing content in the write.

---

## Agentic Variants

Both tools follow the native/agentic pattern.

`FileReadAgent` and `FileWriteAgent` spawn sub-agents with only those tools available, for tasks like "read all Python files in this directory and summarize them" or "write the following files to disk" — where multiple operations are needed in an isolated context window.

These are lower priority than the native tools and can be added in a follow-up pass.

---

## Sandbox Behavior

All four file tools (`FileRead`, `FileWrite`, `FileEdit`, `FileSearch`) share the same `check_path()` enforcement from `nori/tools/_sandbox.py`. In CLI mode, the sandbox root defaults to `cwd`. In agent code, it is unrestricted unless the user passes `sandbox=True` or sets a `sandbox_dir`.

---

## File Layout

```
nori/tools/
    file_read.py      # FileRead
    file_write.py     # FileWrite
```

---

## Open Questions

None. Ready to implement.
