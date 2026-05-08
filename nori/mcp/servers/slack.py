from nori.mcp.server import MCPServer


def Slack(token: str) -> MCPServer:
    return MCPServer(
        name="slack",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-slack"],
        env={"SLACK_BOT_TOKEN": token},
    )
