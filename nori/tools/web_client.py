import httpx

from nori.tool import tool


@tool
async def WebClient(url: str, method: str = "GET", body: str = "") -> str:
    """Make an HTTP request and return the response body."""
    async with httpx.AsyncClient() as client:
        response = await client.request(method, url, content=body or None)
        return f"[{response.status_code}]\n{response.text}"
