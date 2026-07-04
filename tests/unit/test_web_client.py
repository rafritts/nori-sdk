"""Tests for WebClient tool — fully mocked, no network."""

from unittest.mock import AsyncMock, MagicMock, patch
import httpx


def _mock_response(text="", status_code=200, is_redirect=False):
    resp = MagicMock()
    resp.text = text
    resp.status_code = status_code
    resp.is_redirect = is_redirect
    return resp


def _mock_client(get):
    client = AsyncMock()
    client.get = get
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


async def test_web_client_returns_parsed_text():
    from nori.tools.web_client import WebClient

    resp = _mock_response("<html><body><p>Hello world</p></body></html>")
    client = _mock_client(AsyncMock(return_value=resp))

    with patch("nori.tools.web_client.check_url", new=AsyncMock(return_value=None)), \
         patch("httpx.AsyncClient", return_value=client):
        result = await WebClient(url="http://example.com", reason="r")

    assert "Hello world" in result.result


async def test_web_client_network_error_returns_message():
    from nori.tools.web_client import WebClient

    client = _mock_client(AsyncMock(side_effect=httpx.ConnectError("connection refused")))

    with patch("nori.tools.web_client.check_url", new=AsyncMock(return_value=None)), \
         patch("httpx.AsyncClient", return_value=client):
        result = await WebClient(url="http://example.com", reason="r")

    assert "[network error]" in result.result


async def test_web_client_empty_response_returns_status():
    from nori.tools.web_client import WebClient

    resp = _mock_response(text="", status_code=204)
    client = _mock_client(AsyncMock(return_value=resp))

    with patch("nori.tools.web_client.check_url", new=AsyncMock(return_value=None)), \
         patch("httpx.AsyncClient", return_value=client):
        result = await WebClient(url="http://example.com", reason="r")

    assert "204" in result.result
    assert "empty" in result.result


async def test_web_client_blocks_metadata_ip():
    """SSRF guard blocks a literal link-local address with no network/DNS."""
    from nori.tools.web_client import WebClient
    result = await WebClient(url="http://169.254.169.254/latest/meta-data/", reason="r")
    assert "[blocked]" in result.result


async def test_web_client_blocks_loopback():
    from nori.tools.web_client import WebClient
    result = await WebClient(url="http://127.0.0.1:8080/admin", reason="r")
    assert "[blocked]" in result.result


async def test_web_client_blocks_non_http_scheme():
    from nori.tools.web_client import WebClient
    result = await WebClient(url="file:///etc/passwd", reason="r")
    assert "[blocked]" in result.result


async def test_web_client_blocks_redirect_to_internal():
    """A public URL that 302s to a private address is blocked at the hop."""
    from nori.tools.web_client import WebClient

    redirect = _mock_response(status_code=302, is_redirect=True)
    redirect.headers = {"location": "http://169.254.169.254/"}
    redirect.url = httpx.URL("http://example.com")
    client = _mock_client(AsyncMock(return_value=redirect))

    # Only the first check_url (the original public URL) passes; the hop is real-checked.
    async def only_first_ok(url):
        return None if url == "http://example.com" else "[blocked] internal"

    with patch("nori.tools.web_client.check_url", new=AsyncMock(side_effect=only_first_ok)), \
         patch("httpx.AsyncClient", return_value=client):
        result = await WebClient(url="http://example.com", reason="r")

    assert "[blocked]" in result.result


def test_web_client_schema_has_reason_required():
    from nori.tools.web_client import WebClient
    assert "reason" in WebClient.schema["function"]["parameters"]["required"]
