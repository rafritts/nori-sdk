from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

_UNSET = object()


@dataclass
class ServerConfig:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 7731


def _parse_server(value) -> ServerConfig:
    if value is False or value is None:
        return ServerConfig(enabled=False)
    if value is True:
        return ServerConfig(enabled=True)
    if isinstance(value, dict):
        return ServerConfig(enabled=True, **value)
    raise ValueError("server must be True, False, or a dict with host/port keys")


@dataclass
class NotifyConfig:
    slack_webhook: str | None = None
    webhook_url: str | None = None


@dataclass
class AgentDefaults:
    model: object = None  # Model | None, avoid circular import
    tool_timeout: float | None = None
    run_timeout: float | None = None
    max_turns: int | None = None
    tool_models: dict = field(default_factory=dict)  # {tool_class: Model}
    server: ServerConfig = field(default_factory=ServerConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    control_tower: str | None = None
    project: str = "default"


_defaults = AgentDefaults()


def configure(**kwargs) -> None:
    tool_models = kwargs.pop("tool_models", None)
    server = kwargs.pop("server", _UNSET)
    notify = kwargs.pop("notify", _UNSET)
    control_tower = kwargs.pop("control_tower", _UNSET)
    project = kwargs.pop("project", _UNSET)
    for k, v in kwargs.items():
        setattr(_defaults, k, v)
    if tool_models:
        _defaults.tool_models.update(tool_models)
    if server is not _UNSET:
        _defaults.server = _parse_server(server)
    if notify is not _UNSET:
        _defaults.notify = notify if isinstance(notify, NotifyConfig) else NotifyConfig(**notify)
    if control_tower is not _UNSET:
        _defaults.control_tower = control_tower
        if project is not _UNSET:
            _defaults.project = project
        from nori import tower_sink
        tower_sink.configure(control_tower, _defaults.project)
    elif project is not _UNSET:
        _defaults.project = project


def reset() -> None:
    global _defaults
    _defaults = AgentDefaults()


def get_defaults() -> AgentDefaults:
    return _defaults
