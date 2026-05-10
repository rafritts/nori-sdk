import httpx

from nori.tool import tool
from nori.tools.base import ToolResult


@tool
async def WebClient(url: str, method: str = "GET", body: str = "") -> ToolResult:
    """Make an HTTP request and return the response body."""
    async with httpx.AsyncClient() as client:
        response = await client.request(method, url, content=body or None)
    return ToolResult(result=f"[{response.status_code}]\n{response.text}")
