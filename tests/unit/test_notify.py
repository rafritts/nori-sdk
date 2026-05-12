from unittest.mock import AsyncMock, patch, MagicMock

import pytest

import nori
from nori.config import NotifyConfig


@pytest.fixture(autouse=True)
def reset_config():
    yield
    nori.reset()


# ── stdout fallback ───────────────────────────────────────────────────────────

async def test_notify_stdout_fallback(capsys):
    from nori.tools.notify import Notify
    result = await Notify(message="task complete", reason="r")
    assert "stdout" in result.result.lower()
    captured = capsys.readouterr()
    assert "task complete" in captured.out


async def test_notify_stdout_urgent_prefix(capsys):
    from nori.tools.notify import Notify
    await Notify(message="critical failure", urgent=True, reason="r")
    captured = capsys.readouterr()
    assert "URGENT" in captured.out
    assert "critical failure" in captured.out


async def test_notify_stdout_non_urgent_no_urgent_prefix(capsys):
    from nori.tools.notify import Notify
    await Notify(message="done", urgent=False, reason="r")
    captured = capsys.readouterr()
    assert "URGENT" not in captured.out


# ── Slack webhook ─────────────────────────────────────────────────────────────

async def test_notify_slack_posts_message():
    nori.configure(notify=NotifyConfig(slack_webhook="https://hooks.slack.com/test"))
    from nori.tools.notify import Notify

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("nori.tools.notify.httpx.AsyncClient", return_value=mock_client):
        result = await Notify(message="deployed", reason="r")

    assert "Slack" in result.result
    call_kwargs = mock_client.post.call_args
    assert "deployed" in call_kwargs.kwargs["json"]["text"]


async def test_notify_slack_urgent_mentions_channel():
    nori.configure(notify=NotifyConfig(slack_webhook="https://hooks.slack.com/test"))
    from nori.tools.notify import Notify

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("nori.tools.notify.httpx.AsyncClient", return_value=mock_client):
        await Notify(message="fire", urgent=True, reason="r")

    text = mock_client.post.call_args.kwargs["json"]["text"]
    assert "<!channel>" in text


async def test_notify_slack_http_error_returns_error_string():
    import httpx
    nori.configure(notify=NotifyConfig(slack_webhook="https://hooks.slack.com/test"))
    from nori.tools.notify import Notify

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

    with patch("nori.tools.notify.httpx.AsyncClient", return_value=mock_client):
        result = await Notify(message="hi", reason="r")

    assert "[notify error]" in result.result


# ── generic webhook ───────────────────────────────────────────────────────────

async def test_notify_webhook_posts_json():
    nori.configure(notify=NotifyConfig(webhook_url="https://myapp.internal/events"))
    from nori.tools.notify import Notify

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("nori.tools.notify.httpx.AsyncClient", return_value=mock_client):
        result = await Notify(message="step done", urgent=False, reason="r")

    assert "webhook" in result.result.lower()
    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["message"] == "step done"
    assert payload["urgent"] is False
    assert "timestamp" in payload


async def test_notify_slack_takes_priority_over_webhook():
    nori.configure(notify=NotifyConfig(
        slack_webhook="https://hooks.slack.com/test",
        webhook_url="https://myapp.internal/events",
    ))
    from nori.tools.notify import Notify

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("nori.tools.notify.httpx.AsyncClient", return_value=mock_client):
        result = await Notify(message="hello", reason="r")

    assert "Slack" in result.result


# ── config ────────────────────────────────────────────────────────────────────

def test_configure_notify_with_dataclass():
    nori.configure(notify=NotifyConfig(slack_webhook="https://hooks.slack.com/x"))
    assert nori.config.get_defaults().notify.slack_webhook == "https://hooks.slack.com/x"


def test_configure_notify_with_dict():
    nori.configure(notify={"slack_webhook": "https://hooks.slack.com/y"})
    assert nori.config.get_defaults().notify.slack_webhook == "https://hooks.slack.com/y"


def test_notify_schema_has_reason_required():
    from nori.tools.notify import Notify
    assert "reason" in Notify.schema["function"]["parameters"]["required"]


async def test_notify_webhook_http_error_returns_message():
    import httpx
    nori.configure(notify=NotifyConfig(webhook_url="https://myapp.internal/events"))
    from nori.tools.notify import Notify

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

    with patch("nori.tools.notify.httpx.AsyncClient", return_value=mock_client):
        result = await Notify(message="test", reason="r")

    assert "[notify error]" in result.result
    assert "Webhook" in result.result
