"""Stitch 1–4 element crops into a single 2x2 grid image."""

import base64
from io import BytesIO

from PIL import Image as PILImage

_GRID = {1: (1, 1), 2: (1, 2), 3: (2, 2), 4: (2, 2)}
_GAP = 6
_BG = (24, 24, 24)


def compose_grid(
    crops: list[PILImage.Image],
    element_ids: list[str],
    colors: list[tuple[str, str]],
) -> tuple[str, str]:
    """Stitch crops into a grid. Returns (base64_png, legend_text)."""
    n = len(crops)
    rows, cols = _GRID[n]

    cell_w = max(c.width  for c in crops)
    cell_h = max(c.height for c in crops)

    total_w = cols * cell_w + (cols - 1) * _GAP
    total_h = rows * cell_h + (rows - 1) * _GAP

    composite = PILImage.new("RGB", (total_w, total_h), _BG)

    for i, crop in enumerate(crops):
        row = i // cols
        col = i % cols
        x = col * (cell_w + _GAP) + (cell_w - crop.width)  // 2
        y = row * (cell_h + _GAP) + (cell_h - crop.height) // 2
        composite.paste(crop, (x, y))

    buf = BytesIO()
    composite.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    legend = "Screenshot legend: " + ", ".join(
        f"{element_ids[i]}={colors[i][1]}" for i in range(n)
    )
    return b64, legend
