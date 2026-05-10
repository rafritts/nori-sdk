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
    region: str | None = None      # AWS region for Provider.BEDROCK; ignored by all others
    http_client: object | None = None  # custom httpx.AsyncClient; bypasses api_key/base_url auth

    def __post_init__(self):
        if not self.id:
            raise ValueError("Model.id must be a non-empty string.")
        if self.context_window <= 0:
            raise ValueError("Model.context_window must be a positive integer.")

        if self.provider is not None:
            from nori.providers import Provider as P
            if self.provider is P.BEDROCK:
                self._setup_bedrock()
            else:
                self.base_url = self.base_url or self.provider.base_url
                self.api_key = self.api_key or self.provider.api_key

        if self.http_client is not None and self.base_url is None:
            raise ValueError("Model with http_client requires base_url.")
        if self.http_client is None and self.api_key is None and self.base_url is None:
            raise ValueError(
                "Model requires api_key, base_url, or provider. "
                "Example: Model(id='grok-4', provider=Provider.XAI)"
            )

    def __repr__(self) -> str:
        provider_part = f" ({self.provider.name})" if self.provider is not None else ""
        return f"Model(id={self.id!r}{provider_part})"

    def _setup_bedrock(self) -> None:
        import os
        from nori.providers import make_bedrock_http_client
        region = self.region or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        self.region = region
        self.base_url = self.base_url or f"https://bedrock-runtime.{region}.amazonaws.com/openai"
        self.http_client = make_bedrock_http_client(region)
