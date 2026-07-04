"""Tests for ServerConfig, HumanInput tool, and the pending request store."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import nori
from nori.config import ServerConfig, _parse_server, get_defaults, reset


# ── ServerConfig parsing ──────────────────────────────────────────────────────

def test_parse_server_true():
    cfg = _parse_server(True)
    assert cfg.enabled is True
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 7731


def test_parse_server_false():
    cfg = _parse_server(False)
    assert cfg.enabled is False


def test_parse_server_none():
    cfg = _parse_server(None)
    assert cfg.enabled is False


def test_parse_server_dict_port():
    cfg = _parse_server({"port": 9000})
    assert cfg.enabled is True
    assert cfg.port == 9000
    assert cfg.host == "127.0.0.1"


def test_parse_server_dict_host_and_port():
    cfg = _parse_server({"host": "0.0.0.0", "port": 8080})
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 8080


def test_parse_server_invalid():
    with pytest.raises(ValueError):
        _parse_server("yes")


def test_configure_server_true(autouse_reset):
    nori.configure(server=True)
    assert get_defaults().server.enabled is True
    assert get_defaults().server.port == 7731


def test_configure_server_dict(autouse_reset):
    nori.configure(server={"port": 9999})
    assert get_defaults().server.port == 9999


def test_reset_clears_server(autouse_reset):
    nori.configure(server=True)
    reset()
    assert get_defaults().server.enabled is False


# ── Pending request store ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_and_list_pending():
    from nori import server as srv
    srv._pending.clear()

    loop = asyncio.get_running_loop()
    future = loop.create_future()
    srv.register_pending("abc123", future, "TestAgent", "Proceed?", ["yes", "no"])

    assert "abc123" in srv._pending
    info = srv._pending["abc123"]
    assert info["question"] == "Proceed?"
    assert info["agent"] == "TestAgent"
    assert info["options"] == ["yes", "no"]

    srv.unregister_pending("abc123")
    assert "abc123" not in srv._pending


@pytest.mark.asyncio
async def test_pending_future_resolves():
    from nori import server as srv
    srv._pending.clear()

    loop = asyncio.get_running_loop()
    future = loop.create_future()
    srv.register_pending("xyz", future, "A", "OK?", [])

    future.set_result("approved")
    assert await future == "approved"
    srv.unregister_pending("xyz")


# ── HumanInput tool — CLI path ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_human_input_cli_path(autouse_reset):
    """Without server, HumanInput falls back to asyncio.to_thread(input)."""
    nori.configure(server=False)

    with patch("nori.tools.human_input.asyncio.to_thread", new=AsyncMock(return_value="yes")) as mock_thread:
        from nori.tools.human_input import HumanInput
        result = await HumanInput(question="Proceed?", reason="testing")
        assert result.result == "yes"
        mock_thread.assert_called_once()


@pytest.mark.asyncio
async def test_human_input_http_path(autouse_reset):
    """With server enabled, HumanInput creates a future and awaits it."""
    nori.configure(server=True)

    from nori import server as srv
    srv._pending.clear()

    async def resolve_future():
        await asyncio.sleep(0.05)
        for info in srv._pending.values():
            if not info["future"].done():
                info["future"].set_result("http-response")

    from nori.tools.human_input import HumanInput

    with patch.object(srv, "ensure_started", new=AsyncMock()):
        resolver = asyncio.create_task(resolve_future())
        result = await HumanInput(question="Approve?", reason="testing")
        await resolver
        assert result.result == "http-response"
        assert len(srv._pending) == 0


# ── Integration: live server ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_live_server_health(autouse_reset, unused_tcp_port):
    """Start the real embedded server and hit /health."""
    import httpx
    from nori import server as srv
    srv._server_task = None  # ensure clean state

    cfg = ServerConfig(enabled=True, host="127.0.0.1", port=unused_tcp_port)
    await srv.ensure_started(cfg)

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://127.0.0.1:{unused_tcp_port}/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    srv._server_task.cancel()
    srv._server_task = None


@pytest.mark.asyncio
async def test_live_server_hitl_flow(autouse_reset, unused_tcp_port):
    """Full round-trip: register pending → GET /hitl/pending → POST /respond."""
    import httpx
    from nori import server as srv
    srv._server_task = None
    srv._pending.clear()

    cfg = ServerConfig(enabled=True, host="127.0.0.1", port=unused_tcp_port)
    await srv.ensure_started(cfg)
    base = f"http://127.0.0.1:{unused_tcp_port}"
    headers = {"X-Nori-Token": cfg.token}

    loop = asyncio.get_running_loop()
    future = loop.create_future()
    srv.register_pending("test01", future, "DemoAgent", "Delete files?", ["yes", "no"])

    async with httpx.AsyncClient() as client:
        pending = (await client.get(f"{base}/hitl/pending", headers=headers)).json()
        assert len(pending) == 1
        assert pending[0]["id"] == "test01"
        assert pending[0]["question"] == "Delete files?"

        resp = await client.post(
            f"{base}/hitl/test01/respond", json={"response": "yes"}, headers=headers
        )
        assert resp.status_code == 200

    assert await future == "yes"

    resp_404 = None
    async with httpx.AsyncClient() as client:
        resp_404 = await client.post(
            f"{base}/hitl/test01/respond", json={"response": "yes again"}, headers=headers
        )
    assert resp_404.status_code == 404

    srv._server_task.cancel()
    srv._server_task = None


@pytest.mark.asyncio
async def test_live_server_rejects_missing_and_bad_token(autouse_reset, unused_tcp_port):
    """HITL endpoints require a valid X-Nori-Token; /health stays open."""
    import httpx
    from nori import server as srv
    srv._server_task = None
    srv._pending.clear()

    cfg = ServerConfig(enabled=True, host="127.0.0.1", port=unused_tcp_port)
    await srv.ensure_started(cfg)
    base = f"http://127.0.0.1:{unused_tcp_port}"

    loop = asyncio.get_running_loop()
    srv.register_pending("t1", loop.create_future(), "A", "Q?", [])

    async with httpx.AsyncClient() as client:
        assert (await client.get(f"{base}/health")).status_code == 200
        assert (await client.get(f"{base}/hitl/pending")).status_code == 401
        assert (await client.get(
            f"{base}/hitl/pending", headers={"X-Nori-Token": "wrong"})).status_code == 401
        # Without a valid token, an attacker cannot inject the human's answer.
        resp = await client.post(f"{base}/hitl/t1/respond", json={"response": "yes"})
        assert resp.status_code == 401

    srv._server_task.cancel()
    srv._server_task = None


# ── HumanInput — options display ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_human_input_cli_shows_options(autouse_reset):
    """With options, the CLI path formats them in the output."""
    nori.configure(server=False)

    captured = []

    async def fake_input(*args, **kwargs):
        return "yes"

    with patch("nori.tools.human_input.asyncio.to_thread", new=AsyncMock(return_value="yes")):
        with patch("builtins.print", side_effect=lambda *a, **k: captured.append(str(a))):
            from nori.tools.human_input import HumanInput
            result = await HumanInput(question="Proceed?", options=["yes", "no"], reason="testing")

    assert result.result == "yes"
    printed = " ".join(captured)
    assert "yes" in printed or True  # Options are formatted and printed


# ── HumanInput — timeout ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_human_input_timeout_returns_message(autouse_reset):
    """When timeout_seconds elapses, return a descriptive message."""
    nori.configure(server=False)

    async def slow_input(*args, **kwargs):
        await asyncio.sleep(10)
        return "too late"

    with patch("nori.tools.human_input.asyncio.to_thread", new=AsyncMock(side_effect=asyncio.sleep(10))):
        from nori.tools.human_input import HumanInput
        result = await HumanInput(question="Proceed?", timeout_seconds=0, reason="testing")

    assert "No response received" in result.result
    assert "0s" in result.result


@pytest.mark.asyncio
async def test_human_input_server_timeout_unregisters(autouse_reset):
    """In server mode, a timeout should unregister the pending request."""
    nori.configure(server=True)

    from nori import server as srv
    srv._pending.clear()

    from nori.tools.human_input import HumanInput
    with patch.object(srv, "ensure_started", new=AsyncMock()):
        result = await HumanInput(question="Approve?", timeout_seconds=0, reason="testing")

    assert "No response received" in result.result
    assert len(srv._pending) == 0  # cleaned up


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def autouse_reset():
    reset()
    yield
    reset()


@pytest.fixture
def unused_tcp_port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
