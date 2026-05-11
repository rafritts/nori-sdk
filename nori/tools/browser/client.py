"""BrowserClient — Playwright hydration + BeautifulSoup parsing. No LLM."""

from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.browser.parser import html_to_text

_HYDRATION_TIMEOUT = 8_000


@tool
async def BrowserClient(url: str) -> ToolResult:
    """Fetch a JS-rendered page, wait for hydration, and return clean readable text. No interaction — use BrowserAgent for multi-step tasks."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return ToolResult(result="playwright is not installed: run `uv add playwright && playwright install chromium`")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        try:
            await page.goto(url, wait_until="domcontentloaded")
            try:
                await page.wait_for_load_state("networkidle", timeout=_HYDRATION_TIMEOUT)
            except Exception:
                pass  # proceed even if the page never fully idles
            html = await page.content()
        finally:
            await browser.close()

    return ToolResult(result=html_to_text(html))
