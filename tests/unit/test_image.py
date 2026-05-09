import base64
import math
from io import BytesIO

import pytest

from nori.image import Image
from nori.enums import ResizeMode


def _make_png(width: int, height: int) -> bytes:
    from PIL import Image as PILImage
    img = PILImage.new("RGB", (width, height), color=(128, 64, 32))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── Construction validation ───────────────────────────────────────────────────

def test_requires_exactly_one_source():
    with pytest.raises(ValueError):
        Image()  # none set

def test_requires_exactly_one_source_not_two():
    with pytest.raises(ValueError):
        Image(path="/a.png", url="https://example.com/a.png")

def test_invalid_detail():
    with pytest.raises(ValueError):
        Image(path="/a.png", detail="ultra")

def test_valid_construction_path():
    img = Image(path="/tmp/a.png")
    assert img.path == "/tmp/a.png"
    assert img.resize == ResizeMode.MODERATE

def test_valid_construction_data():
    img = Image(data=b"\x89PNG")
    assert img.data == b"\x89PNG"

def test_valid_construction_url():
    img = Image(url="https://example.com/img.png")
    assert img.url == "https://example.com/img.png"


# ── estimated_tokens ─────────────────────────────────────────────────────────

def test_estimated_tokens_low_detail():
    img = Image(path="/a.png", detail="low")
    assert img.estimated_tokens() == 85

def test_estimated_tokens_512x512():
    img = Image(path="/a.png", detail="auto")
    assert img.estimated_tokens((512, 512)) == math.ceil(512/512) * math.ceil(512/512) * 170 + 85

def test_estimated_tokens_1024x768():
    img = Image(path="/a.png", detail="auto")
    assert img.estimated_tokens((1024, 768)) == math.ceil(1024/512) * math.ceil(768/512) * 170 + 85


# ── to_content_part ───────────────────────────────────────────────────────────

def test_data_uri_passthrough():
    uri = "data:image/jpeg;base64,abc123"
    img = Image(url=uri)
    part = img.to_content_part()
    assert part["type"] == "image_url"
    assert part["image_url"]["url"] == uri

def test_no_strip_marker_by_default():
    uri = "data:image/jpeg;base64,abc123"
    img = Image(url=uri)
    part = img.to_content_part()
    assert "_strip" not in part

def test_strip_marker_when_remove_from_context():
    uri = "data:image/jpeg;base64,abc123"
    img = Image(url=uri, remove_from_context_after_read=True)
    part = img.to_content_part()
    assert part.get("_strip") is True

def test_encodes_raw_bytes(tmp_path):
    png = _make_png(200, 100)
    img = Image(data=png, resize=ResizeMode.NONE)
    part = img.to_content_part()
    url = part["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    decoded = base64.b64decode(url.split(",", 1)[1])
    assert len(decoded) > 0

def test_resize_reduces_dimensions(tmp_path):
    from PIL import Image as PILImage
    png = _make_png(2000, 1500)
    img = Image(data=png, resize=ResizeMode.AGGRESSIVE, output_format="jpeg")
    part = img.to_content_part()
    url = part["image_url"]["url"]
    decoded = base64.b64decode(url.split(",", 1)[1])
    result = PILImage.open(BytesIO(decoded))
    assert max(result.size) <= ResizeMode.AGGRESSIVE

def test_no_resize_when_mode_none():
    from PIL import Image as PILImage
    png = _make_png(300, 200)
    img = Image(data=png, resize=ResizeMode.NONE)
    part = img.to_content_part()
    decoded = base64.b64decode(part["image_url"]["url"].split(",", 1)[1])
    result = PILImage.open(BytesIO(decoded))
    assert result.size == (300, 200)

def test_path_encoding(tmp_path):
    path = tmp_path / "test.png"
    path.write_bytes(_make_png(100, 100))
    img = Image(path=str(path))
    part = img.to_content_part()
    assert part["image_url"]["url"].startswith("data:image/jpeg;base64,")

def test_detail_passed_through():
    img = Image(url="data:image/jpeg;base64,abc", detail="low")
    part = img.to_content_part()
    assert part["image_url"]["detail"] == "low"


# ── ResizeMode ────────────────────────────────────────────────────────────────

def test_resize_mode_is_int():
    assert int(ResizeMode.AGGRESSIVE) == 512
    assert int(ResizeMode.MODERATE) == 1024
    assert int(ResizeMode.LIGHT) == 2048
    assert int(ResizeMode.NONE) == 0

def test_resize_mode_usable_as_int():
    img = Image(data=_make_png(2000, 2000), resize=768)
    from PIL import Image as PILImage
    part = img.to_content_part()
    decoded = base64.b64decode(part["image_url"]["url"].split(",", 1)[1])
    result = PILImage.open(BytesIO(decoded))
    assert max(result.size) <= 768
