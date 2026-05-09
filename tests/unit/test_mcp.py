import pytest

from nori import Agent, Model
from nori.mcp.server import MCPServer


def test_mcpserver_stdio_construction():
    s = MCPServer(name="git", command="npx", args=["-y", "@modelcontextprotocol/server-git"])
    assert s.name == "git"
    assert s.command == "npx"
    assert s.args == ["-y", "@modelcontextprotocol/server-git"]


def test_mcpserver_url_construction():
    s = MCPServer(name="remote", url="http://localhost:8080/sse")
    assert s.url == "http://localhost:8080/sse"


def test_mcpserver_requires_command_or_url():
    with pytest.raises(ValueError):
        MCPServer(name="broken")


def test_reason_injected_into_discovered_schema():
    schema = {
        "type": "function",
        "function": {
            "name": "list_issues",
            "description": "List GitHub issues.",
            "parameters": {
                "type": "object",
                "properties": {"repo": {"type": "string"}},
                "required": ["repo"],
            },
        },
    }
    result = Agent._inject_reason_into_schema(schema)
    assert "reason" in result["function"]["parameters"]["properties"]
    assert "reason" in result["function"]["parameters"]["required"]


def test_reason_not_duplicated_if_already_present():
    schema = {
        "type": "function",
        "function": {
            "name": "tool",
            "description": "A tool.",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
            },
        },
    }
    result = Agent._inject_reason_into_schema(schema)
    assert result["function"]["parameters"]["required"].count("reason") == 1


def test_add_mcp_server():
    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"))
    s = MCPServer(name="github", command="npx", args=["-y", "@modelcontextprotocol/server-github"])
    agent.add_mcp_server(s)
    assert s in agent.mcp_servers


def test_remove_mcp_server():
    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"))
    s = MCPServer(name="github", command="npx", args=[])
    agent.add_mcp_server(s)
    agent.remove_mcp_server("github")
    assert s not in agent.mcp_servers
