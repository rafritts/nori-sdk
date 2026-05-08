from nori.mcp.server import MCPServer
from nori.mcp.servers.brave_search import BraveSearch
from nori.mcp.servers.filesystem import Filesystem
from nori.mcp.servers.github import GitHub
from nori.mcp.servers.postgres import Postgres
from nori.mcp.servers.slack import Slack
from nori.mcp.servers.sqlite import SQLite


def test_github_returns_mcpserver():
    s = GitHub(token="ghp_token")
    assert isinstance(s, MCPServer)
    assert s.name == "github"
    assert s.env["GITHUB_PERSONAL_ACCESS_TOKEN"] == "ghp_token"


def test_filesystem_returns_mcpserver():
    s = Filesystem(path="/tmp")
    assert isinstance(s, MCPServer)
    assert s.name == "filesystem"
    assert "/tmp" in s.args


def test_postgres_returns_mcpserver():
    s = Postgres(connection_string="postgresql://localhost/db")
    assert isinstance(s, MCPServer)
    assert s.name == "postgres"
    assert "postgresql://localhost/db" in s.args


def test_sqlite_returns_mcpserver():
    s = SQLite(db_path="/tmp/test.db")
    assert isinstance(s, MCPServer)
    assert s.name == "sqlite"
    assert "/tmp/test.db" in s.args


def test_slack_returns_mcpserver():
    s = Slack(token="xoxb-token")
    assert isinstance(s, MCPServer)
    assert s.name == "slack"
    assert s.env["SLACK_BOT_TOKEN"] == "xoxb-token"


def test_brave_search_returns_mcpserver():
    s = BraveSearch(api_key="brave_key")
    assert isinstance(s, MCPServer)
    assert s.name == "brave-search"
    assert s.env["BRAVE_API_KEY"] == "brave_key"


def test_all_factories_have_command():
    factories = [
        GitHub("t"), Filesystem("/tmp"), Postgres("pg://x"),
        SQLite("/x.db"), Slack("t"), BraveSearch("k"),
    ]
    for s in factories:
        assert s.command, f"{s.name} missing command"
