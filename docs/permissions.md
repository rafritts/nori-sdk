# Permissions

Nori's permission system lets you restrict which tools an agent can call. You provide either an allow list or a deny list — never both. Passing both raises a `RuntimeError` at construction.

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
# Allow all file tools, block everything else
Permissions(allow=["file_*"])

# Block all write operations
Permissions(deny=["*_write", "*_delete", "file_edit"])
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
