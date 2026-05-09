import base64
import logging
import math
from dataclasses import dataclass
from io import BytesIO

from nori.enums import ResizeMode

logger = logging.getLogger("nori.image")


@dataclass
class Image:
    path: str | None = None
    url: str | None = None
    data: bytes | None = None

    detail: str = "auto"
    resize: ResizeMode | int = ResizeMode.MODERATE
    output_format: str = "jpeg"
    remove_from_context_after_read: bool = False

    def __post_init__(self):
        sources = sum(x is not None for x in [self.path, self.url, self.data])
        if sources != 1:
            raise ValueError("Exactly one of path, url, or data must be set.")
        if self.detail not in ("auto", "low", "high"):
            raise ValueError("detail must be 'auto', 'low', or 'high'.")

    def _load_raw_bytes(self) -> bytes:
        if self.data is not None:
            return self.data
        if self.url is not None:
            if self.url.startswith("data:"):
                _, encoded = self.url.split(",", 1)
                return base64.b64decode(encoded)
            import urllib.request
            with urllib.request.urlopen(self.url) as resp:
                return resp.read()
        with open(self.path, "rb") as f:
            return f.read()

    def estimated_tokens(self, size: tuple[int, int] | None = None) -> int:
        if self.detail == "low":
            return 85
        if size is None:
            dim = self.resize if self.resize > 0 else 4096
            size = (dim, dim)
        w, h = size
        return math.ceil(w / 512) * math.ceil(h / 512) * 170 + 85

    def to_content_part(self) -> dict:
        if self.url and self.url.startswith("data:"):
            data_uri = self.url
        else:
            data_uri = self._encode()

        part: dict = {"type": "image_url", "image_url": {"url": data_uri, "detail": self.detail}}
        if self.remove_from_context_after_read:
            part["_strip"] = True
        return part

    def _encode(self) -> str:
        raw = self._load_raw_bytes()

        try:
            from PIL import Image as PILImage
        except ImportError:
            raise ImportError("pillow is required for image support: uv add pillow")

        img = PILImage.open(BytesIO(raw))

        if self.resize > 0:
            w, h = img.size
            if max(w, h) > self.resize:
                scale = self.resize / max(w, h)
                img = img.resize((int(w * scale), int(h * scale)), PILImage.LANCZOS)

        est = self.estimated_tokens(img.size)
        if est > 1000:
            logger.warning(
                "Image will use ~%d tokens after resize to %dx%d",
                est, img.size[0], img.size[1],
            )

        buf = BytesIO()
        fmt = self.output_format.upper()
        if fmt == "JPEG":
            img = img.convert("RGB")
            img.save(buf, format="JPEG", quality=85)
            mime = "image/jpeg"
        else:
            img.save(buf, format=fmt)
            mime = f"image/{fmt.lower()}"

        encoded = base64.b64encode(buf.getvalue()).decode()
        return f"data:{mime};base64,{encoded}"
