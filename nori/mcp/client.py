"""MCP client — connects to an MCPServer, discovers its tools, and exposes
each one as a Nori-callable tool (an object with `.schema`, `.summarize_output`,
and an async `__call__`, matching the @tool / BoundTool interface).

The `mcp` SDK is an optional dependency. Install with `nori-sdk[mcp]`.
"""

import asyncio
import logging
import os

from nori.mcp.server import MCPServer

logger = logging.getLogger("nori.mcp")


def _result_to_text(result) -> str:
    """Flatten an MCP CallToolResult into a string for the model."""
    parts = []
    for block in result.content or []:
        text = getattr(block, "text", None)
        parts.append(text if text is not None else str(block))
    text = "\n".join(parts) if parts else "[no content]"
    if getattr(result, "isError", False):
        return f"[MCP tool error] {text}"
    return text


def _tool_to_schema(remote_tool) -> dict:
    """Convert an MCP Tool definition into an OpenAI function schema."""
    params = remote_tool.inputSchema or {"type": "object", "properties": {}}
    return {
        "type": "function",
        "function": {
            "name": remote_tool.name,
            "description": remote_tool.description or "",
            "parameters": params,
        },
    }


class MCPTool:
    """A single tool discovered on an MCP server, callable like a native @tool."""

    def __init__(self, session, remote_name: str, schema: dict, server_name: str):
        self._session = session
        self._remote_name = remote_name
        self.schema = schema
        self.server_name = server_name
        self.summarize_output = True

    async def __call__(self, **kwargs) -> str:
        kwargs.pop("reason", None)
        kwargs.pop("summary", None)
        result = await self._session.call_tool(self._remote_name, kwargs)
        return _result_to_text(result)

    def __repr__(self):
        return f"MCPTool({self.server_name}:{self._remote_name})"


def _transport(server: MCPServer):
    """Return the async-context-manager transport for a server config."""
    try:
        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:  # pragma: no cover - import guard
        raise ImportError(
            "MCP support requires the 'mcp' package. Install with: pip install 'nori-sdk[mcp]'"
        ) from exc

    if server.url:
        # SSE for legacy `/sse` endpoints, streamable HTTP otherwise (current spec).
        if server.url.rstrip("/").endswith("/sse"):
            from mcp.client.sse import sse_client
            return sse_client(server.url)
        from mcp.client.streamable_http import streamablehttp_client
        return streamablehttp_client(server.url)

    params = StdioServerParameters(
        command=server.command,
        args=server.args,
        env={**os.environ, **server.env},
    )
    return stdio_client(params)


class MCPConnection:
    """An open connection to one MCP server, alive for the duration of the agent run.

    The transport and session are anyio context managers whose cancel scopes must
    be entered and exited in the same task. We therefore own the entire lifecycle
    inside a single dedicated task (`_run`) and signal it to close via an event;
    tool calls dispatch onto the live session from whatever task invokes them.
    """

    def __init__(self, server: MCPServer):
        self.server = server
        self.tools: list[MCPTool] = []
        self._session = None
        self._task: asyncio.Task | None = None
        self._ready = asyncio.Event()
        self._closing = asyncio.Event()
        self._error: BaseException | None = None

    async def connect(self) -> list[MCPTool]:
        """Open the transport, handshake, and discover tools. Raises on failure."""
        self._task = asyncio.create_task(self._run())
        await self._ready.wait()
        if self._error is not None:
            raise self._error
        return self.tools

    async def _run(self) -> None:
        from mcp import ClientSession

        from nori.agent import Agent

        try:
            async with _transport(self.server) as transport:
                read, write = transport[0], transport[1]
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._session = session
                    resp = await session.list_tools()
                    for remote_tool in resp.tools:
                        schema = Agent._inject_reason_into_schema(_tool_to_schema(remote_tool))
                        self.tools.append(MCPTool(session, remote_tool.name, schema, self.server.name))
                    self._ready.set()
                    await self._closing.wait()
        except BaseException as exc:  # noqa: BLE001 - surfaced to connect()/logged
            self._error = exc
        finally:
            self._ready.set()

    async def aclose(self) -> None:
        self._closing.set()
        if self._task is not None:
            await self._task
            self._task = None
