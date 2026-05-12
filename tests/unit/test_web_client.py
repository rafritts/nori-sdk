"""Tests for WebClient tool — fully mocked, no network."""

from unittest.mock import AsyncMock, MagicMock, patch
import httpx


async def test_web_client_returns_parsed_text():
    from nori.tools.web_client import WebClient

    mock_response = MagicMock()
    mock_response.text = "<html><body><p>Hello world</p></body></html>"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await WebClient(url="http://example.com", reason="r")

    assert "Hello world" in result.result


async def test_web_client_network_error_returns_message():
    from nori.tools.web_client import WebClient

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await WebClient(url="http://example.com", reason="r")

    assert "[network error]" in result.result


async def test_web_client_empty_response_returns_status():
    from nori.tools.web_client import WebClient

    mock_response = MagicMock()
    mock_response.text = ""
    mock_response.status_code = 204

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await WebClient(url="http://example.com", reason="r")

    assert "204" in result.result
    assert "empty" in result.result


def test_web_client_schema_has_reason_required():
    from nori.tools.web_client import WebClient
    assert "reason" in WebClient.schema["function"]["parameters"]["required"]
