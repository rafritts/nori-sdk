import httpx

from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.browser.parser import html_to_text


@tool
async def WebClient(url: str) -> ToolResult:
    """Fetch a plain HTML page and return clean readable text. No JS hydration — use BrowserClient for JS-rendered sites."""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(url)
    except httpx.HTTPError as e:
        return ToolResult(result=f"[network error] {e}")

    if not response.text:
        return ToolResult(result=f"[{response.status_code}] empty response")

    return ToolResult(result=html_to_text(response.text))
