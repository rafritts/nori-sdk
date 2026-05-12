# SPEC-15: Notify Tool

## Motivation

Production agents often run unattended on long-horizon tasks — deploying code, processing datasets, running incident triage. When they finish (or fail), there's no built-in way to reach a human. Users have to poll, tail logs, or wrap the agent in their own notification glue.

`Notify` closes this gap. It is a first-class tool that sends a message to a human-readable destination — Slack, a webhook, or stdout — so agents can signal completion, request attention, or report status without requiring any external library setup from the user.

---

## Design

### Single tool, multiple backends

`Notify` dispatches to the configured backend. Backend is set at the `nori.configure()` level, not per-call. The agent doesn't know or care which backend is active — it just calls `Notify`.

```python
nori.configure(notify=NotifyConfig(slack_webhook="https://hooks.slack.com/..."))

agent = Agent(name="deployer", tools=[Bash, Notify, ...])
```

The agent then calls:

```python
Notify(message="Deploy complete. Service is healthy. 3 pods running.")
Notify(message="Deploy failed at migration step. Human review needed.", urgent=True)
```

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `message` | str | yes | The message to send |
| `urgent` | bool | no | Hint to backend that this warrants immediate attention. Default: False. |
| `reason` | str | yes | Injected by framework |

### Backends

**Slack (webhook)**

Posts to a Slack incoming webhook URL. `urgent=True` prepends `<!channel>` to mention the channel.

```python
NotifyConfig(slack_webhook="https://hooks.slack.com/services/...")
```

**Webhook (generic)**

HTTP POST to any URL with JSON body:
```json
{ "message": "...", "urgent": false, "agent": "deployer", "timestamp": "..." }
```

```python
NotifyConfig(webhook_url="https://myapp.internal/agent-events")
```

**stdout (default fallback)**

If no backend is configured, prints to stdout with a `[Notify]` prefix. This makes `Notify` safe to include in any agent without configuration — it degrades gracefully.

```
[Notify] Deploy complete. Service is healthy. 3 pods running.
```

### NotifyConfig

```python
@dataclass
class NotifyConfig:
    slack_webhook: str | None = None
    webhook_url: str | None = None
    # If both are set, Slack takes priority.
```

Added to `AgentDefaults` alongside existing config fields.

---

## What's out of scope

- **Email** — SMTP setup is user-specific and adds dependency weight. Users who need email should use a webhook or a Slack email integration.
- **PagerDuty / OpsGenie** — these are MCP territory, not framework built-ins.
- **Per-agent backend** — backend is set globally via `nori.configure()`. Agents within the same process share the same notification channel. Overriding per-agent is not supported in v1.
- **Delivery guarantees** — if the webhook fails, `Notify` returns an error string in the `ToolResult` and the agent can decide what to do. No retry logic.

---

## File Layout

```
nori/tools/
    notify.py         # Notify tool
nori/
    config.py         # add NotifyConfig, add notify field to AgentDefaults
```

---

## Open Questions

None. Ready to implement.
