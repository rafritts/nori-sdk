from dataclasses import dataclass, field

import nori.config as config
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
        self.api_key = self.api_key or config.API_KEY
        if self.api_key is None and self.base_url is None:
            raise ValueError(
                "Model requires either api_key or base_url. "
                "Pass one directly or set NORI_API_KEY in the environment."
            )
        if self.context_window <= 0:
            raise ValueError("Model.context_window must be a positive integer.")
