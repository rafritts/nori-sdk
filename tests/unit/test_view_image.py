"""Tests for make_view_image / ViewImage tool — fully mocked, no API calls."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest


def _make_model():
    from nori.model import Model
    return Model(id="test-model", api_key="test-key", base_url="http://localhost/v1")


def _make_view_image(model=None):
    from nori.tools.view_image import make_view_image
    m = model or _make_model()
    with patch("openai.AsyncOpenAI"):
        return make_view_image(m)


def _mock_completion(text="image description"):
    choice = MagicMock()
    choice.message.content = text
    completion = MagicMock()
    completion.choices = [choice]
    return completion


# ── schema ────────────────────────────────────────────────────────────────────

def test_view_image_schema_has_required_fields():
    tool = _make_view_image()
    required = tool.schema["function"]["parameters"]["required"]
    assert "path" in required
    assert "prompt" in required
    assert "reason" in required
    assert "summary" in required


def test_view_image_schema_name():
    tool = _make_view_image()
    assert tool.schema["function"]["name"] == "ViewImage"


def test_view_image_summarize_output_false():
    tool = _make_view_image()
    assert tool.summarize_output is False


# ── URL path ──────────────────────────────────────────────────────────────────

async def test_view_image_url_path():
    model = _make_model()
    with patch("openai.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=_mock_completion("a sunset"))
        MockOpenAI.return_value = mock_client

        from nori.tools.view_image import make_view_image
        tool = make_view_image(model)

    with patch("nori.image.Image") as MockImage:
        mock_img = MagicMock()
        mock_img.to_content_part.return_value = {"type": "image_url", "image_url": {"url": "https://example.com/img.png"}}
        MockImage.return_value = mock_img
        mock_client.chat.completions.create = AsyncMock(return_value=_mock_completion("a sunset"))

        result = await tool(path="https://example.com/img.png", prompt="describe it", reason="r")

    assert "sunset" in result.result


async def test_view_image_local_path(tmp_path):
    model = _make_model()
    fake_image = tmp_path / "img.png"
    fake_image.write_bytes(b"fake png data")

    with patch("openai.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        completion = _mock_completion("a cat sitting")
        mock_client.chat.completions.create = AsyncMock(return_value=completion)
        MockOpenAI.return_value = mock_client

        from nori.tools.view_image import make_view_image
        tool = make_view_image(model)

    with patch("nori.image.Image") as MockImage:
        mock_img = MagicMock()
        mock_img.to_content_part.return_value = {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
        MockImage.return_value = mock_img
        mock_client.chat.completions.create = AsyncMock(return_value=_mock_completion("a cat sitting"))

        result = await tool(path=str(fake_image), prompt="what is this?", reason="r")

    assert "cat" in result.result


async def test_view_image_sandbox_violation(tmp_path):
    from nori.tools._sandbox import sandbox_dir

    model = _make_model()
    with patch("openai.AsyncOpenAI"):
        from nori.tools.view_image import make_view_image
        tool = make_view_image(model)

    token = sandbox_dir.set(str(tmp_path))
    try:
        result = await tool(path="/etc/passwd", prompt="what is this?", reason="r")
        assert "[error]" in result.result
        assert "Sandbox violation" in result.result
    finally:
        sandbox_dir.reset(token)


async def test_view_image_empty_response(tmp_path):
    model = _make_model()
    fake_image = tmp_path / "img.png"
    fake_image.write_bytes(b"fake png")

    choice = MagicMock()
    choice.message.content = None
    completion = MagicMock()
    completion.choices = [choice]

    with patch("openai.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=completion)
        MockOpenAI.return_value = mock_client

        from nori.tools.view_image import make_view_image
        tool = make_view_image(model)

    with patch("nori.image.Image") as MockImage:
        mock_img = MagicMock()
        mock_img.to_content_part.return_value = {"type": "image_url", "image_url": {}}
        MockImage.return_value = mock_img
        mock_client.chat.completions.create = AsyncMock(return_value=completion)

        result = await tool(path=str(fake_image), prompt="describe", reason="r")

    assert result.result == ""
