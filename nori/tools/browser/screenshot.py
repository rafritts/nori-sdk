"""Element-scoped screenshots with colored borders."""

import base64
from io import BytesIO

from PIL import Image as PILImage, ImageDraw
from playwright.async_api import Page

PALETTE: list[tuple[str, str]] = [
    ("#FF3B30", "red"),
    ("#007AFF", "blue"),
    ("#34C759", "green"),
    ("#FF9500", "orange"),
]

_PADDING = 60
_MAX_DIM = 400
_BORDER = 4


async def crop_element(page: Page, bbox: dict, color_hex: str) -> PILImage.Image:
    """Crop the region around bbox, draw a colored border, return a PIL Image."""
    vp = page.viewport_size or {"width": 1280, "height": 800}

    x1 = max(0, bbox["x"] - _PADDING)
    y1 = max(0, bbox["y"] - _PADDING)
    x2 = min(vp["width"],  bbox["x"] + bbox["w"] + _PADDING)
    y2 = min(vp["height"], bbox["y"] + bbox["h"] + _PADDING)

    png = await page.screenshot(
        clip={"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1},
        type="png",
    )

    img = PILImage.open(BytesIO(png))

    if max(img.width, img.height) > _MAX_DIM:
        scale = _MAX_DIM / max(img.width, img.height)
        img = img.resize((int(img.width * scale), int(img.height * scale)), PILImage.LANCZOS)

    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, img.width - 1, img.height - 1], outline=color_hex, width=_BORDER)

    return img


async def full_page_screenshot(page: Page) -> str:
    """Full viewport screenshot, resized to max 1280px wide. Returns base64 PNG."""
    png = await page.screenshot(type="png")
    img = PILImage.open(BytesIO(png))

    if img.width > 1280:
        scale = 1280 / img.width
        img = img.resize((1280, int(img.height * scale)), PILImage.LANCZOS)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()
