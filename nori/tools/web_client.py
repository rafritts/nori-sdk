import httpx

from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools._ssrf import check_url
from nori.tools.browser.parser import html_to_text

_MAX_REDIRECTS = 5


@tool
async def WebClient(url: str) -> ToolResult:
    """Fetch a plain HTML page and return clean readable text. No JS hydration — use BrowserClient for JS-rendered sites."""
    blocked = await check_url(url)
    if blocked:
        return ToolResult(result=blocked)

    try:
        # Follow redirects manually so each hop is SSRF-checked before we fetch it.
        async with httpx.AsyncClient(follow_redirects=False) as client:
            response = await client.get(url)
            hops = 0
            while response.is_redirect and hops < _MAX_REDIRECTS:
                location = response.headers.get("location")
                if not location:
                    break
                next_url = str(response.url.join(location))
                blocked = await check_url(next_url)
                if blocked:
                    return ToolResult(result=blocked)
                response = await client.get(next_url)
                hops += 1
    except httpx.HTTPError as e:
        return ToolResult(result=f"[network error] {e}")

    if not response.text:
        return ToolResult(result=f"[{response.status_code}] empty response")

    return ToolResult(result=html_to_text(response.text))
