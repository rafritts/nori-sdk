import httpx

from nori.tool import tool
from nori.tools.base import ToolResult


@tool
async def ApiClient(url: str, method: str = "GET", body: str = "", headers: str = "") -> ToolResult:
    """Make a raw HTTP request and return the status code and response body. Use for APIs and custom requests."""
    import json as _json
    parsed_headers = {}
    if headers:
        try:
            parsed_headers = _json.loads(headers)
        except _json.JSONDecodeError:
            return ToolResult(result="[error] headers must be a JSON object string")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method, url, content=body or None, headers=parsed_headers, follow_redirects=True,
            )
        return ToolResult(result=f"[{response.status_code}]\n{response.text}")
    except httpx.HTTPError as e:
        return ToolResult(result=f"[network error] {e}")
