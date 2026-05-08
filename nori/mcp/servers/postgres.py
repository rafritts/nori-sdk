from nori.mcp.server import MCPServer


def Postgres(connection_string: str) -> MCPServer:
    return MCPServer(
        name="postgres",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-postgres", connection_string],
    )
