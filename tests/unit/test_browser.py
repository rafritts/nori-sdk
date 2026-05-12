"""Unit tests for BrowserAgent/BrowserClient tool modules (no live browser required)."""

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image as PILImage

from nori.tools.browser.blocklist import TRACKING_FRAGMENTS
from nori.tools.browser.compositor import compose_grid
from nori.tools.browser.prompts import build_state_message, format_elements
from nori.tools.browser.screenshot import PALETTE


# ── blocklist ────────────────────────────────────────────────────────────────

def test_blocklist_is_frozenset():
    assert isinstance(TRACKING_FRAGMENTS, frozenset)

def test_blocklist_contains_expected_entries():
    assert "google-analytics.com" in TRACKING_FRAGMENTS
    assert "hotjar.com" in TRACKING_FRAGMENTS
    assert "doubleclick.net" in TRACKING_FRAGMENTS

def test_blocklist_does_not_contain_legitimate_domains():
    assert "example.com" not in TRACKING_FRAGMENTS
    assert "github.com"  not in TRACKING_FRAGMENTS


# ── extractor filtering ──────────────────────────────────────────────────────

def test_tracking_href_filtered():
    from nori.tools.browser.extractor import _is_tracking
    assert _is_tracking("https://www.google-analytics.com/collect")
    assert _is_tracking("https://hotjar.com/track")
    assert not _is_tracking("https://example.com/login")
    assert not _is_tracking(None)


# ── prompts ──────────────────────────────────────────────────────────────────

def test_format_elements_empty():
    assert format_elements([]) == "[]"

def test_format_elements_single():
    el = {"id": "el_0", "tag": "button", "text": "Login", "bbox": {"x": 0, "y": 0, "w": 80, "h": 30}}
    out = format_elements([el])
    assert "el_0" in out
    assert "Login" in out

def test_build_state_message_contains_task_and_url():
    elements = [{"id": "el_0", "tag": "a", "text": "Home", "bbox": {"x": 0, "y": 0, "w": 50, "h": 20}}]
    msg = build_state_message("find notifications", "https://x.com/home", elements, [])
    assert "find notifications" in msg
    assert "https://x.com/home" in msg
    assert "el_0" in msg

def test_build_state_message_includes_recent_history():
    history = ["navigate: ok", "click: ok", "type: ok"]
    msg = build_state_message("task", "https://x.com", [], history)
    assert "navigate: ok" in msg

def test_build_state_message_caps_history_at_six():
    history = [f"action_{i}: ok" for i in range(10)]
    msg = build_state_message("task", "https://x.com", [], history)
    # Only last 6 should appear
    assert "action_9: ok" in msg
    assert "action_0: ok" not in msg


# ── compositor ───────────────────────────────────────────────────────────────

def _dummy_crop(color=(200, 100, 100), size=(100, 100)) -> PILImage.Image:
    return PILImage.new("RGB", size, color)

def test_compose_grid_single():
    crops = [_dummy_crop()]
    b64, legend = compose_grid(crops, ["el_0"], [PALETTE[0]])
    img_bytes = base64.b64decode(b64)
    assert len(img_bytes) > 0
    assert "el_0=red" in legend

def test_compose_grid_two():
    crops = [_dummy_crop(), _dummy_crop((0, 100, 200))]
    b64, legend = compose_grid(crops, ["el_0", "el_1"], PALETTE[:2])
    assert "el_0=red" in legend
    assert "el_1=blue" in legend
    img = PILImage.open(__import__("io").BytesIO(base64.b64decode(b64)))
    # 1x2 grid: width should be ~2x a single crop
    assert img.width > 100

def test_compose_grid_four():
    crops = [_dummy_crop() for _ in range(4)]
    b64, legend = compose_grid(crops, [f"el_{i}" for i in range(4)], PALETTE)
    assert "el_3=orange" in legend
    img = PILImage.open(__import__("io").BytesIO(base64.b64decode(b64)))
    # 2x2 grid
    assert img.width > 100
    assert img.height > 100

def test_compose_grid_three_uses_2x2_layout():
    crops = [_dummy_crop() for _ in range(3)]
    b64, legend = compose_grid(crops, ["el_0", "el_1", "el_2"], PALETTE[:3])
    img = PILImage.open(__import__("io").BytesIO(base64.b64decode(b64)))
    # 2x2 layout: width ~= 2 * cell_w + gap
    assert img.width >= 200

def test_compose_grid_legend_order_matches_palette():
    crops = [_dummy_crop(), _dummy_crop()]
    _, legend = compose_grid(crops, ["el_5", "el_9"], PALETTE[:2])
    assert legend.index("el_5=red") < legend.index("el_9=blue")


# ── palette ──────────────────────────────────────────────────────────────────

def test_palette_has_four_entries():
    assert len(PALETTE) == 4

def test_palette_entries_are_hex_and_name():
    for hex_color, name in PALETTE:
        assert hex_color.startswith("#")
        assert len(hex_color) == 7
        assert isinstance(name, str)


# ── actions ──────────────────────────────────────────────────────────────────

def test_find_element_returns_none_for_unknown_id():
    from nori.tools.browser.actions import _find
    elements = [{"id": "el_0", "tag": "button", "bbox": {}}]
    assert _find("el_99", elements) is None
    assert _find(None, elements) is None

def test_find_element_returns_correct_element():
    from nori.tools.browser.actions import _find
    elements = [
        {"id": "el_0", "tag": "a", "bbox": {}},
        {"id": "el_1", "tag": "button", "bbox": {}},
    ]
    assert _find("el_1", elements)["tag"] == "button"


@pytest.mark.asyncio
async def test_execute_action_unknown_returns_error():
    from nori.tools.browser.actions import execute_action
    page = MagicMock()
    err = await execute_action(page, {"action": "fly"}, [])
    assert "unknown action" in err

@pytest.mark.asyncio
async def test_execute_action_click_missing_element_returns_error():
    from nori.tools.browser.actions import execute_action
    page = MagicMock()
    err = await execute_action(page, {"action": "click", "element_id": "el_99"}, [])
    assert "not found" in err

@pytest.mark.asyncio
async def test_execute_action_navigate_missing_url_returns_error():
    from nori.tools.browser.actions import execute_action
    page = MagicMock()
    err = await execute_action(page, {"action": "navigate", "url": ""}, [])
    assert err is not None


# ── parser ───────────────────────────────────────────────────────────────────

def test_parser_strips_scripts_and_styles():
    from nori.tools.browser.parser import html_to_text
    html = "<html><body><script>alert(1)</script><style>body{}</style><p>Hello world</p></body></html>"
    result = html_to_text(html)
    assert "Hello world" in result
    assert "alert" not in result
    assert "body{}" not in result

def test_parser_strips_nav_and_footer():
    from nori.tools.browser.parser import html_to_text
    html = "<html><body><nav>Menu</nav><main><p>Content</p></main><footer>Footer</footer></body></html>"
    result = html_to_text(html)
    assert "Content" in result
    assert "Menu" not in result
    assert "Footer" not in result

def test_parser_collapses_blank_lines():
    from nori.tools.browser.parser import html_to_text
    html = "<html><body><p>A</p><p></p><p></p><p>B</p></body></html>"
    result = html_to_text(html)
    assert "\n\n\n" not in result

def test_parser_truncates_long_output():
    from nori.tools.browser.parser import html_to_text, _MAX_CHARS
    long_text = "x " * 10_000
    html = f"<html><body><p>{long_text}</p></body></html>"
    result = html_to_text(html)
    assert len(result) <= _MAX_CHARS + 100  # small buffer for truncation message
    assert "truncated" in result

def test_parser_empty_html_returns_empty():
    from nori.tools.browser.parser import html_to_text
    result = html_to_text("<html><body></body></html>")
    assert result == ""

@pytest.mark.asyncio
async def test_execute_action_wait_clamps_to_5s():
    from nori.tools.browser.actions import execute_action
    page = MagicMock()
    with patch("nori.tools.browser.actions.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await execute_action(page, {"action": "wait", "ms": 99999}, [])
        mock_sleep.assert_called_once_with(5.0)

@pytest.mark.asyncio
async def test_execute_action_scroll_clamps_px():
    from nori.tools.browser.actions import execute_action
    page = AsyncMock()
    page.mouse = AsyncMock()
    await execute_action(page, {"action": "scroll", "direction": "down", "px": 9999}, [])
    page.mouse.wheel.assert_called_once_with(0, 2000)


@pytest.mark.asyncio
async def test_execute_action_scroll_up():
    from nori.tools.browser.actions import execute_action
    page = AsyncMock()
    page.mouse = AsyncMock()
    await execute_action(page, {"action": "scroll", "direction": "up", "px": 400}, [])
    page.mouse.wheel.assert_called_once_with(0, -400)


@pytest.mark.asyncio
async def test_execute_action_click_success():
    from nori.tools.browser.actions import execute_action
    page = AsyncMock()
    page.mouse = AsyncMock()
    elements = [{"id": "el_0", "tag": "button", "bbox": {"x": 100, "y": 50, "w": 80, "h": 30}}]
    result = await execute_action(page, {"action": "click", "element_id": "el_0"}, elements)
    assert result is None
    page.mouse.click.assert_called_once_with(140.0, 65.0)


@pytest.mark.asyncio
async def test_execute_action_type_success():
    from nori.tools.browser.actions import execute_action
    page = AsyncMock()
    page.mouse = AsyncMock()
    page.keyboard = AsyncMock()
    elements = [{"id": "el_0", "tag": "input", "bbox": {"x": 10, "y": 10, "w": 200, "h": 40}}]
    result = await execute_action(page, {"action": "type", "element_id": "el_0", "text": "hello"}, elements)
    assert result is None
    page.keyboard.type.assert_called_once()


@pytest.mark.asyncio
async def test_execute_action_type_missing_element():
    from nori.tools.browser.actions import execute_action
    page = AsyncMock()
    err = await execute_action(page, {"action": "type", "element_id": "el_99", "text": "x"}, [])
    assert "not found" in err


@pytest.mark.asyncio
async def test_execute_action_navigate_success():
    from nori.tools.browser.actions import execute_action
    page = AsyncMock()
    result = await execute_action(page, {"action": "navigate", "url": "https://example.com"}, [])
    assert result is None
    page.goto.assert_called_once()


@pytest.mark.asyncio
async def test_execute_action_select_missing_element():
    from nori.tools.browser.actions import execute_action
    page = AsyncMock()
    err = await execute_action(page, {"action": "select", "element_id": "el_99", "value": "x"}, [])
    assert "not found" in err


@pytest.mark.asyncio
async def test_execute_action_select_success():
    from nori.tools.browser.actions import execute_action
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=True)
    elements = [{"id": "el_0", "tag": "select", "bbox": {"x": 10, "y": 10, "w": 100, "h": 30}}]
    result = await execute_action(page, {"action": "select", "element_id": "el_0", "value": "opt1"}, elements)
    assert result is None


@pytest.mark.asyncio
async def test_execute_action_select_fails():
    from nori.tools.browser.actions import execute_action
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=False)
    elements = [{"id": "el_0", "tag": "select", "bbox": {"x": 10, "y": 10, "w": 100, "h": 30}}]
    result = await execute_action(page, {"action": "select", "element_id": "el_0", "value": "opt1"}, elements)
    assert "select failed" in result


# ── extractor ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_elements_filters_tracking():
    from nori.tools.browser.extractor import extract_elements
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=[
        {"id": "el_0", "tag": "a", "href": "https://google-analytics.com/collect", "bbox": {}},
        {"id": "el_1", "tag": "a", "href": "https://example.com/home", "bbox": {}},
    ])
    result = await extract_elements(page)
    assert len(result) == 1
    assert result[0]["id"] == "el_1"


# ── screenshot ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_crop_element_returns_image():
    from io import BytesIO
    from PIL import Image as PILImage
    from nori.tools.browser.screenshot import crop_element

    buf = BytesIO()
    PILImage.new("RGB", (200, 200), (255, 0, 0)).save(buf, format="PNG")
    png_bytes = buf.getvalue()

    page = AsyncMock()
    page.viewport_size = {"width": 1280, "height": 800}
    page.screenshot = AsyncMock(return_value=png_bytes)

    bbox = {"x": 100, "y": 100, "w": 50, "h": 50}
    img = await crop_element(page, bbox, "#FF3B30")
    assert img.width > 0
    assert img.height > 0


@pytest.mark.asyncio
async def test_full_page_screenshot_returns_base64():
    from io import BytesIO
    from PIL import Image as PILImage
    from nori.tools.browser.screenshot import full_page_screenshot

    buf = BytesIO()
    PILImage.new("RGB", (800, 600), (0, 128, 255)).save(buf, format="PNG")
    png_bytes = buf.getvalue()

    page = AsyncMock()
    page.screenshot = AsyncMock(return_value=png_bytes)

    result = await full_page_screenshot(page)
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_full_page_screenshot_resizes_wide_image():
    from io import BytesIO
    from PIL import Image as PILImage
    from nori.tools.browser.screenshot import full_page_screenshot
    import base64

    buf = BytesIO()
    PILImage.new("RGB", (2000, 1000), (200, 200, 200)).save(buf, format="PNG")
    png_bytes = buf.getvalue()

    page = AsyncMock()
    page.screenshot = AsyncMock(return_value=png_bytes)

    result = await full_page_screenshot(page)
    img = PILImage.open(BytesIO(base64.b64decode(result)))
    assert img.width == 1280


# ── BrowserClient — playwright not installed ──────────────────────────────────

@pytest.mark.asyncio
async def test_browser_client_playwright_not_installed():
    from nori.tools.browser.client import BrowserClient
    with patch("builtins.__import__", side_effect=lambda name, *a, **k: (_ for _ in ()).throw(ImportError("no playwright")) if name == "playwright.async_api" else __import__(name, *a, **k)):
        result = await BrowserClient(url="http://example.com", reason="r")
    assert "playwright" in result.result.lower()
