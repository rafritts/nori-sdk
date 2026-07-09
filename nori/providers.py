import os
from dataclasses import dataclass
from enum import Enum


class Provider(Enum):
    # (base_url, env_var)
    OPENAI     = ("https://api.openai.com/v1",                                "OPENAI_API_KEY")
    ANTHROPIC  = ("https://api.anthropic.com/v1",                             "ANTHROPIC_API_KEY")
    XAI        = ("https://api.x.ai/v1",                                      "XAI_API_KEY")
    GROQ       = ("https://api.groq.com/openai/v1",                           "GROQ_API_KEY")
    DEEPSEEK   = ("https://api.deepseek.com/v1",                              "DEEPSEEK_API_KEY")
    GOOGLE     = ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY")
    OPENROUTER = ("https://openrouter.ai/api/v1",                             "OPENROUTER_API_KEY")
    KIMI       = ("https://api.moonshot.cn/v1",                               "KIMI_API_KEY")
    MINIMAX    = ("https://api.minimax.chat/v1",                              "MINIMAX_API_KEY")
    GLM        = ("https://open.bigmodel.cn/api/paas/v4/",                   "GLM_API_KEY")
    QWEN       = ("https://dashscope-intl.aliyuncs.com/compatible-mode/v1",  "QWEN_API_KEY")
    OLLAMA     = ("http://localhost:11434/v1",                                "OLLAMA_API_KEY")
    # base_url is region-dependent; built at Model init time. api_key not used (SigV4 auth).
    BEDROCK    = ("__bedrock__",                                              None)

    @property
    def base_url(self) -> str:
        return self.value[0]

    @property
    def api_key(self) -> str | None:
        env_var = self.value[1]
        return os.getenv(env_var) if env_var else None


def make_bedrock_http_client(region: str) -> object:
    """Return an httpx.AsyncClient that signs every request with AWS SigV4.

    Credentials are resolved by boto3 in priority order:
      1. AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY env vars
      2. ~/.aws/credentials profile
      3. IAM instance / task role (ECS, EC2, Lambda)
    """
    try:
        import boto3
        import botocore.auth
        import botocore.awsrequest
        import httpx
    except ImportError:
        raise ImportError(
            "boto3 is required for Provider.BEDROCK. "
            "Install it with: uv add boto3"
        )

    class _SigV4Auth(httpx.Auth):
        def __init__(self, session, region: str) -> None:
            self._creds = session.get_credentials()
            self._region = region

        def auth_flow(self, request: "httpx.Request"):
            creds = self._creds.get_frozen_credentials()
            aws_req = botocore.awsrequest.AWSRequest(
                method=request.method,
                url=str(request.url),
                data=request.content,
                headers=dict(request.headers),
            )
            botocore.auth.SigV4Auth(creds, "bedrock", self._region).add_auth(aws_req)
            for k, v in aws_req.headers.items():
                request.headers[k] = v
            yield request

    return httpx.AsyncClient(auth=_SigV4Auth(boto3.Session(), region))


# ── Pricing ───────────────────────────────────────────────────────────────────
# $ per 1M tokens, input and output. Unknown models return 0.0.
# Groq, OpenRouter, and Ollama are omitted: variable/free pricing.

@dataclass(frozen=True)
class _Price:
    prompt: float
    completion: float


_PRICING: dict[str, _Price] = {
    # OpenAI
    "gpt-5.5":                      _Price(prompt=5.00,  completion=30.00),
    "gpt-5.4":                      _Price(prompt=2.50,  completion=15.00),
    "gpt-5.4-mini":                 _Price(prompt=0.75,  completion=4.50),
    "gpt-5.4-nano":                 _Price(prompt=0.20,  completion=1.25),
    # Anthropic
    "claude-opus-4-7":              _Price(prompt=5.00,  completion=25.00),
    "claude-opus-4-6":              _Price(prompt=5.00,  completion=25.00),
    "claude-sonnet-4-6":            _Price(prompt=3.00,  completion=15.00),
    "claude-haiku-4-5":             _Price(prompt=1.00,  completion=5.00),
    # xAI
    "grok-4.3":                     _Price(prompt=1.25,  completion=2.50),
    "grok-4-1-fast-reasoning":      _Price(prompt=0.20,  completion=0.50),
    # Google
    "gemini-3.1-flash-lite":        _Price(prompt=0.25,  completion=1.50),
    "gemini-3.1-pro-preview":       _Price(prompt=2.00,  completion=12.00),
    # DeepSeek
    "DeepSeek-V4-Flash":            _Price(prompt=0.14,  completion=0.28),
    "DeepSeek-V4-Pro":              _Price(prompt=1.74,  completion=3.48),
    # Kimi (Moonshot)
    "kimi-k2.6":                    _Price(prompt=0.95,  completion=4.00),
    # MiniMax
    "MiniMax-M2.7":                 _Price(prompt=0.30,  completion=1.20),
    # GLM (Zhipu)
    "glm-5.1":                      _Price(prompt=1.40,  completion=4.40),
    # Qwen (Alibaba)
    "qwen3.6-plus":                 _Price(prompt=0.50,  completion=3.00),
}


# xAI (and some others) report exact billed cost as integer ticks.
# 1 USD = 10^10 ticks. See https://docs.x.ai/developers/cost-tracking
USD_TICKS_PER_DOLLAR = 10_000_000_000


def cost_from_ticks(ticks: int) -> float:
    return ticks / USD_TICKS_PER_DOLLAR


def cost_for(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    *,
    reasoning_tokens: int = 0,
) -> float:
    """Estimate USD cost from token counts using the static price table.

    Reasoning tokens (chain-of-thought) are billed at the completion/output rate
    on xAI and are *not* included in ``completion_tokens``.
    Prefer ``cost_from_ticks`` when the provider returns ``cost_in_usd_ticks``.
    """
    price = _PRICING.get(model, _Price(prompt=0.0, completion=0.0))
    output = completion_tokens + reasoning_tokens
    return (prompt_tokens * price.prompt + output * price.completion) / 1_000_000
