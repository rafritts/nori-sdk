# MCP

Nori supports the Model Context Protocol (MCP) as a first-class concept. An `MCPServer` is an explicit object — no magic string inference, no hidden config files.

MCP support requires the optional `mcp` extra:

```bash
pip install "nori-sdk[mcp]"
```

When you pass `mcp_servers=` to an `Agent`, Nori connects to each server at the start of `run()`, discovers its tools via the MCP `tools/list` handshake, and registers them as native tools the model can call (each gets the standard `reason`/`summary` narration fields injected). Tool calls are dispatched over the live connection, and all servers are torn down when the run finishes. A server that fails to connect is logged and skipped — it won't abort the run. Both stdio (`command`/`args`) and HTTP/SSE (`url`) transports are supported.

```python
from nori.mcp import MCPServer

agent = Agent(
    name="MyAgent",
    system_prompt="...",
    tools=[...],
    mcp_servers=[
        MCPServer(
            name="github",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={"GITHUB_PERSONAL_ACCESS_TOKEN": "your_token"},
        )
    ],
)
```

---

## `MCPServer`

```python
@dataclass
class MCPServer:
    name: str
    command: str = ""       # for stdio transport
    args: list[str] = []    # for stdio transport
    env: dict[str, str] = {}
    url: str = ""           # for HTTP/SSE transport
```

Either `command` (stdio) or `url` (HTTP/SSE) is required. Passing neither raises a `ValueError` at construction.

**Stdio:**
```python
MCPServer(
    name="filesystem",
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"],
)
```

**HTTP/SSE:**
```python
MCPServer(
    name="my-server",
    url="http://localhost:8080/mcp",
)
```

---

## Curated factories

Nori includes ready-made factory functions for common MCP servers so you don't have to look up the package names and args:

```python
from nori.mcp.servers.github import GitHub
from nori.mcp.servers.filesystem import Filesystem
from nori.mcp.servers.postgres import Postgres
from nori.mcp.servers.sqlite import SQLite
from nori.mcp.servers.slack import Slack
from nori.mcp.servers.brave_search import BraveSearch

agent = Agent(
    name="MyAgent",
    system_prompt="...",
    mcp_servers=[
        GitHub(token="your_token"),
        Filesystem(path="/workspace"),
        Postgres(connection_string="postgresql://..."),
    ],
)
```

Each factory returns a fully configured `MCPServer` — pass the result directly to `mcp_servers=`.
