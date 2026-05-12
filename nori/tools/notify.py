import datetime
import logging

import httpx

import nori.config as config
from nori.tool import tool
from nori.tools.base import ToolResult

logger = logging.getLogger("nori.notify")

_AGENT_NAME_FALLBACK = "nori-agent"


@tool
async def Notify(message: str, urgent: bool = False) -> ToolResult:
    """Send a notification message to the configured destination (Slack, webhook,
    or stdout). Use to signal task completion, failures, or status updates to a
    human operator. Set urgent=True to request immediate attention."""
    cfg = config.get_defaults().notify

    if cfg.slack_webhook:
        return await _send_slack(cfg.slack_webhook, message, urgent)
    if cfg.webhook_url:
        return await _send_webhook(cfg.webhook_url, message, urgent)
    return _send_stdout(message, urgent)


async def _send_slack(webhook_url: str, message: str, urgent: bool) -> ToolResult:
    text = f"<!channel> {message}" if urgent else message
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(webhook_url, json={"text": text}, timeout=10)
            resp.raise_for_status()
        return ToolResult(result="Notification sent via Slack.")
    except httpx.HTTPError as e:
        logger.warning("Slack notification failed: %s", e)
        return ToolResult(result=f"[notify error] Slack delivery failed: {e}")


async def _send_webhook(webhook_url: str, message: str, urgent: bool) -> ToolResult:
    payload = {
        "message": message,
        "urgent": urgent,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(webhook_url, json=payload, timeout=10)
            resp.raise_for_status()
        return ToolResult(result="Notification sent via webhook.")
    except httpx.HTTPError as e:
        logger.warning("Webhook notification failed: %s", e)
        return ToolResult(result=f"[notify error] Webhook delivery failed: {e}")


def _send_stdout(message: str, urgent: bool) -> ToolResult:
    prefix = "[Notify][URGENT]" if urgent else "[Notify]"
    print(f"{prefix} {message}")
    return ToolResult(result="Notification printed to stdout.")
