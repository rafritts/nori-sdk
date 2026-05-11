"""Extract interactive elements from a Playwright page into a compact JSON list."""

from typing import Any

from playwright.async_api import Page

from nori.tools.browser.blocklist import TRACKING_FRAGMENTS

# Runs in the browser context — extracts interactive elements with attributes + bounding boxes.
_EXTRACT_JS = """
() => {
    const selectors = [
        'a', 'button', 'input', 'select', 'textarea',
        '[role="button"]', '[role="link"]', '[role="tab"]', '[role="menuitem"]',
        '[onclick]'
    ].join(', ');

    const seen = new Set();
    const elements = Array.from(document.querySelectorAll(selectors));
    const results = [];
    let idx = 0;

    for (const el of elements) {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;

        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) continue;

        const tag  = el.tagName.toLowerCase();
        const text = (el.textContent || el.value || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
        const href = el.href || null;

        const key = tag + '|' + text + '|' + (href || '');
        if (seen.has(key)) continue;
        seen.add(key);

        const item = {
            id:   'el_' + idx++,
            tag:  tag,
            bbox: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
        };

        if (text)                          item.text        = text;
        if (href)                          item.href        = href;
        if (el.placeholder)                item.placeholder = el.placeholder;
        if (el.getAttribute('aria-label')) item.aria_label  = el.getAttribute('aria-label');
        if (el.name)                       item.name        = el.name;
        if (el.type && el.type !== 'text') item.type        = el.type;

        results.push(item);
        if (results.length >= 60) break;
    }
    return results;
}
"""


def _is_tracking(href: str | None) -> bool:
    if not href:
        return False
    lower = href.lower()
    return any(frag in lower for frag in TRACKING_FRAGMENTS)


async def extract_elements(page: Page) -> list[dict[str, Any]]:
    raw: list[dict] = await page.evaluate(_EXTRACT_JS)
    return [el for el in raw if not _is_tracking(el.get("href"))]
