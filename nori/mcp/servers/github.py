from nori.mcp.server import MCPServer


def GitHub(token: str) -> MCPServer:
    return MCPServer(
        name="github",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={"GITHUB_PERSONAL_ACCESS_TOKEN": token},
    )
