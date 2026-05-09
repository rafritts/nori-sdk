from dataclasses import dataclass, field

from nori.enums import ContextWindow


@dataclass
class Model:
    id: str
    api_key: str | None = None
    base_url: str | None = None
    context_window: int = ContextWindow.M1

    def __post_init__(self):
        if not self.id:
            raise ValueError("Model.id must be a non-empty string.")
        if self.api_key is None and self.base_url is None:
            raise ValueError(
                "Model requires either api_key or base_url. "
                "Pass api_key directly or use Provider.<name>.api_key."
            )
        if self.context_window <= 0:
            raise ValueError("Model.context_window must be a positive integer.")
