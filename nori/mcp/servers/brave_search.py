from nori.mcp.server import MCPServer


def BraveSearch(api_key: str) -> MCPServer:
    return MCPServer(
        name="brave-search",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-brave-search"],
        env={"BRAVE_API_KEY": api_key},
    )
