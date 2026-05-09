from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from nori.enums import ContextWindow

if TYPE_CHECKING:
    from nori.providers import Provider


@dataclass
class Model:
    id: str
    api_key: str | None = None
    base_url: str | None = None
    context_window: int = ContextWindow.M1
    provider: Provider | None = None

    def __post_init__(self):
        if self.provider is not None:
            self.base_url = self.base_url or self.provider.base_url
            self.api_key = self.api_key or self.provider.api_key
        if not self.id:
            raise ValueError("Model.id must be a non-empty string.")
        if self.api_key is None and self.base_url is None:
            raise ValueError(
                "Model requires api_key, base_url, or provider. "
                "Example: Model(id='grok-4', provider=Provider.XAI)"
            )
        if self.context_window <= 0:
            raise ValueError("Model.context_window must be a positive integer.")
