from nori.mcp.server import MCPServer


def SQLite(db_path: str) -> MCPServer:
    return MCPServer(
        name="sqlite",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-sqlite", db_path],
    )
