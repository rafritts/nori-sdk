from types import SimpleNamespace

from nori import Agent, Model
from nori.mcp.server import MCPServer
from nori.mcp.client import MCPTool, MCPConnection, _result_to_text, _tool_to_schema


def _model():
    return Model(id="grok-4.3", api_key="test-key")


# ── schema / result conversion ──────────────────────────────────────────────

def test_tool_to_schema_converts_fields():
    remote = SimpleNamespace(
        name="list_issues",
        description="List GitHub issues.",
        inputSchema={"type": "object", "properties": {"repo": {"type": "string"}}, "required": ["repo"]},
    )
    schema = _tool_to_schema(remote)
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "list_issues"
    assert schema["function"]["description"] == "List GitHub issues."
    assert schema["function"]["parameters"]["properties"]["repo"] == {"type": "string"}


def test_tool_to_schema_defaults_missing_input_schema():
    remote = SimpleNamespace(name="ping", description=None, inputSchema=None)
    schema = _tool_to_schema(remote)
    assert schema["function"]["description"] == ""
    assert schema["function"]["parameters"] == {"type": "object", "properties": {}}


def test_result_to_text_joins_text_blocks():
    result = SimpleNamespace(
        content=[SimpleNamespace(text="line one"), SimpleNamespace(text="line two")],
        isError=False,
    )
    assert _result_to_text(result) == "line one\nline two"


def test_result_to_text_marks_errors():
    result = SimpleNamespace(content=[SimpleNamespace(text="boom")], isError=True)
    assert _result_to_text(result).startswith("[MCP tool error]")


def test_result_to_text_empty_content():
    result = SimpleNamespace(content=[], isError=False)
    assert _result_to_text(result) == "[no content]"


# ── MCPTool ─────────────────────────────────────────────────────────────────

class _FakeSession:
    def __init__(self):
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return SimpleNamespace(content=[SimpleNamespace(text="ok")], isError=False)


async def test_mcptool_call_strips_meta_and_dispatches():
    session = _FakeSession()
    schema = {"type": "function", "function": {"name": "echo", "parameters": {}}}
    tool = MCPTool(session, "echo", schema, "demo")

    out = await tool(text="hi", reason="because", summary="echoing hi")

    assert out == "ok"
    assert session.calls == [("echo", {"text": "hi"})]
    assert tool.summarize_output is True


# ── MCPConnection.connect ─────────────────────────────────────────────────────

class _AsyncCM:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *exc):
        return False


async def test_connection_connect_registers_tools_with_reason(monkeypatch):
    import mcp

    session = _FakeSession()

    async def fake_initialize():
        return None

    async def fake_list_tools():
        remote = SimpleNamespace(
            name="search",
            description="Search the web.",
            inputSchema={"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
        )
        return SimpleNamespace(tools=[remote])

    session.initialize = fake_initialize
    session.list_tools = fake_list_tools

    # Transport yields (read, write); ClientSession(...) yields the fake session.
    monkeypatch.setattr("nori.mcp.client._transport", lambda server: _AsyncCM(("read", "write")))
    monkeypatch.setattr(mcp, "ClientSession", lambda r, w: _AsyncCM(session))

    conn = MCPConnection(MCPServer(name="demo", command="true"))
    tools = await conn.connect()

    assert len(tools) == 1
    t = tools[0]
    assert t.schema["function"]["name"] == "search"
    # reason/summary injected by Agent._inject_reason_into_schema
    props = t.schema["function"]["parameters"]["properties"]
    assert "reason" in props and "summary" in props
    assert "reason" in t.schema["function"]["parameters"]["required"]

    await conn.aclose()


# ── Agent connect / disconnect lifecycle ──────────────────────────────────────

async def test_agent_connect_disconnect_registers_and_cleans_up(monkeypatch):
    session = _FakeSession()
    schema = Agent._inject_reason_into_schema(
        {"type": "function", "function": {"name": "remote_tool", "description": "x", "parameters": {"type": "object", "properties": {}}}}
    )
    fake_tool = MCPTool(session, "remote_tool", schema, "demo")

    closed = {"v": False}

    async def fake_connect(self):
        self.tools = [fake_tool]
        return self.tools

    async def fake_aclose(self):
        closed["v"] = True

    monkeypatch.setattr(MCPConnection, "connect", fake_connect)
    monkeypatch.setattr(MCPConnection, "aclose", fake_aclose)

    agent = Agent(name="T", model=_model(), mcp_servers=[MCPServer(name="demo", command="true")])
    assert "remote_tool" not in agent._tools

    await agent._connect_mcp()
    assert agent._tools["remote_tool"] is fake_tool

    await agent._disconnect_mcp()
    assert "remote_tool" not in agent._tools
    assert closed["v"] is True


async def test_agent_connect_failure_is_isolated(monkeypatch):
    async def boom(self):
        raise RuntimeError("server unavailable")

    async def fake_aclose(self):
        return None

    monkeypatch.setattr(MCPConnection, "connect", boom)
    monkeypatch.setattr(MCPConnection, "aclose", fake_aclose)

    agent = Agent(name="T", model=_model(), mcp_servers=[MCPServer(name="demo", command="true")])
    # A failing server must not raise — it is logged and skipped.
    await agent._connect_mcp()
    assert agent._mcp_connections == []


def test_mcp_servers_param_populates_list():
    s = MCPServer(name="github", command="npx", args=[])
    agent = Agent(name="T", model=_model(), mcp_servers=[s])
    assert agent.mcp_servers == [s]
