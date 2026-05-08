from nori.mcp.server import MCPServer


def Filesystem(path: str) -> MCPServer:
    return MCPServer(
        name="filesystem",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", path],
    )
