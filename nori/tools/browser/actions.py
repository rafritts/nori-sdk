"""Execute browser actions from LLM-produced action dicts."""

import asyncio

from playwright.async_api import Page

_SELECT_JS = """
([x, y, value]) => {
    const el = document.elementFromPoint(x, y);
    if (!el || el.tagName.toLowerCase() !== 'select') return false;
    el.value = value;
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
}
"""


def _find(element_id: str | None, elements: list[dict]) -> dict | None:
    if not element_id:
        return None
    return next((el for el in elements if el["id"] == element_id), None)


def _center(bbox: dict) -> tuple[float, float]:
    return bbox["x"] + bbox["w"] / 2, bbox["y"] + bbox["h"] / 2


async def execute_action(page: Page, action: dict, elements: list[dict]) -> str | None:
    """Execute one browser action. Returns an error string on failure, None on success."""
    name = action.get("action", "")

    if name == "click":
        el = _find(action.get("element_id"), elements)
        if el is None:
            return f"element {action.get('element_id')} not found"
        cx, cy = _center(el["bbox"])
        await page.mouse.click(cx, cy)

    elif name == "type":
        el = _find(action.get("element_id"), elements)
        if el is None:
            return f"element {action.get('element_id')} not found"
        cx, cy = _center(el["bbox"])
        await page.mouse.click(cx, cy)
        await page.keyboard.type(action.get("text", ""), delay=30)

    elif name == "select":
        el = _find(action.get("element_id"), elements)
        if el is None:
            return f"element {action.get('element_id')} not found"
        cx, cy = _center(el["bbox"])
        ok = await page.evaluate(_SELECT_JS, [cx, cy, action.get("value", "")])
        if not ok:
            return "select failed — element not found at coordinates or not a <select>"

    elif name == "scroll":
        px = min(action.get("px", 400), 2000)
        delta = px if action.get("direction", "down") == "down" else -px
        await page.mouse.wheel(0, delta)

    elif name == "navigate":
        url = action.get("url", "")
        if not url:
            return "navigate requires a url"
        await page.goto(url, wait_until="domcontentloaded")

    elif name == "wait":
        ms = min(action.get("ms", 1000), 5000)
        await asyncio.sleep(ms / 1000)

    else:
        return f"unknown action: {name}"

    return None
