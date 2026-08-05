# Permissions

Nori's permission system lets you restrict which tools an agent can call. You provide either an allow list or a deny list — never both. Passing both to `Permissions(...)` raises a `ValueError` at construction.

Matching uses each tool's schema **function name** (e.g. `Bash`, `FileRead`, or the name of a `@tool` function).

```python
from nori import Agent, Permissions
```

---

## Allow list

Only the tools named in `allow` can be called. Everything else is blocked.

```python
agent = Agent(
    name="ReadOnlyAgent",
    system_prompt="You are a file agent.",
    tools=[read_file, write_file, delete_file],
    permissions=Permissions(allow=["read_file"]),
)
```

If the agent tries to call `write_file` or `delete_file`, a `ToolPermissionError` is raised and the run halts.

For built-ins, use the tool names as registered:

```python
from nori.tools.file_read import FileRead
from nori.tools.web_search import WebSearch

Permissions(allow=["FileRead", "WebSearch"])
```

---

## Deny list

All tools are available except those named in `deny`.

```python
agent = Agent(
    name="NoDeleteAgent",
    system_prompt="You are a file agent.",
    tools=[read_file, write_file, delete_file],
    permissions=Permissions(deny=["delete_file"]),
)
```

---

## Glob patterns

Both allow and deny support `fnmatch` glob patterns:

```python
# Allow all tools whose names start with File
Permissions(allow=["File*"])

# Block write-style tools
Permissions(deny=["FileWrite", "FileEdit", "*_write", "*_delete"])
```

---

## Handling `ToolPermissionError`

When a blocked tool is called, `ToolPermissionError` propagates up from `agent.run()`:

```python
from nori.exceptions import ToolPermissionError

try:
    result = await agent.run("Write to disk, then read it back, then delete it.")
except ToolPermissionError as e:
    print(f"Blocked: {e}")
```

---

See [`permissions_demo.py`](https://github.com/rafritts/nori-sdk/blob/master/demos/permissions_demo.py) for all three scenarios — no restrictions, allow list, and deny list — with real agents.
