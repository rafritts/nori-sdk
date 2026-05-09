from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class AgentDefaults:
    model: object = None  # Model | None, avoid circular import
    tool_timeout: float | None = None
    run_timeout: float | None = None
    max_turns: int | None = None
    tool_models: dict = field(default_factory=dict)  # {tool_class: Model}


_defaults = AgentDefaults()


def configure(**kwargs) -> None:
    tool_models = kwargs.pop("tool_models", None)
    for k, v in kwargs.items():
        setattr(_defaults, k, v)
    if tool_models:
        _defaults.tool_models.update(tool_models)


def reset() -> None:
    global _defaults
    _defaults = AgentDefaults()


def get_defaults() -> AgentDefaults:
    return _defaults
