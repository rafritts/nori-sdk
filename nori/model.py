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
                env_var = self.provider.value[1]
                if self.api_key is None and env_var is not None:
                    raise ValueError(
                        f"Model is set to use {self.provider.name}, but no API key was found. "
                        f"I checked the {env_var} environment variable (system env var, .env file, "
                        f"and os.environ) and it isn't set.\n\n"
                        f"To fix this, do one of:\n"
                        f"  1. Export it in your shell: export {env_var}=your-key-here\n"
                        f"  2. Add it to a .env file in your project root: {env_var}=your-key-here\n"
                        f"  3. Pass it directly: Model(id={self.id!r}, provider=Provider.{self.provider.name}, api_key='your-key-here')"
                    )

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
