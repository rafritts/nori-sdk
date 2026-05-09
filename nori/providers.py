import os
from dataclasses import dataclass
from enum import Enum


class Provider(Enum):
    # (base_url, env_var)
    OPENAI     = ("https://api.openai.com/v1",                                "OPENAI_API_KEY")
    ANTHROPIC  = ("https://api.anthropic.com/v1",                             "ANTHROPIC_API_KEY")
    XAI        = ("https://api.x.ai/v1",                                      "XAI_API_KEY")
    GROQ       = ("https://api.groq.com/openai/v1",                           "GROQ_API_KEY")
    MISTRAL    = ("https://api.mistral.ai/v1",                                "MISTRAL_API_KEY")
    DEEPSEEK   = ("https://api.deepseek.com/v1",                              "DEEPSEEK_API_KEY")
    GOOGLE     = ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY")
    OPENROUTER = ("https://openrouter.ai/api/v1",                             "OPENROUTER_API_KEY")
    KIMI       = ("https://api.moonshot.cn/v1",                               "KIMI_API_KEY")
    MINIMAX    = ("https://api.minimax.chat/v1",                              "MINIMAX_API_KEY")
    GLM        = ("https://open.bigmodel.cn/api/paas/v4/",                   "GLM_API_KEY")
    QWEN       = ("https://dashscope-intl.aliyuncs.com/compatible-mode/v1",  "QWEN_API_KEY")
    OLLAMA     = ("http://localhost:11434/v1",                                "OLLAMA_API_KEY")

    @property
    def base_url(self) -> str:
        return self.value[0]

    @property
    def api_key(self) -> str | None:
        env_var = self.value[1]
        return os.getenv(env_var) if env_var else None


# ── Pricing ───────────────────────────────────────────────────────────────────
# $ per 1M tokens, input and output. Unknown models return 0.0.
# Groq, OpenRouter, and Ollama are omitted: variable/free pricing.

@dataclass(frozen=True)
class _Price:
    prompt: float
    completion: float


_PRICING: dict[str, _Price] = {
    # OpenAI
    "gpt-4o":                       _Price(prompt=2.50,  completion=10.00),
    "gpt-4o-mini":                  _Price(prompt=0.15,  completion=0.60),
    # Anthropic
    "claude-opus-4-7":              _Price(prompt=5.00,  completion=25.00),
    "claude-sonnet-4-6":            _Price(prompt=3.00,  completion=15.00),
    "claude-haiku-4-5":             _Price(prompt=1.00,  completion=4.00),
    # xAI
    "grok-4.3":                     _Price(prompt=1.25,  completion=2.50),
    "grok-4-1-fast-reasoning":      _Price(prompt=0.20,  completion=0.50),
    # Google
    "gemini-3.1-pro":               _Price(prompt=1.25,  completion=10.00),
    "gemini-2.5-flash":             _Price(prompt=0.075, completion=0.30),
    # Mistral
    "mistral-large-latest":         _Price(prompt=0.50,  completion=1.50),
    "mistral-small-latest":         _Price(prompt=0.10,  completion=0.30),
    # DeepSeek
    "deepseek-chat":                _Price(prompt=0.14,  completion=0.28),
    "deepseek-reasoner":            _Price(prompt=0.55,  completion=2.19),
    # Kimi (Moonshot)
    "kimi-k2":                      _Price(prompt=0.95,  completion=4.00),
    # MiniMax
    "MiniMax-M1":                   _Price(prompt=0.30,  completion=1.20),
    # GLM (Zhipu)
    "glm-4-plus":                   _Price(prompt=0.60,  completion=2.20),
    # Qwen (Alibaba)
    "qwen-max":                     _Price(prompt=0.40,  completion=1.60),
    "qwen-plus":                    _Price(prompt=0.07,  completion=0.21),
}


def cost_for(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    price = _PRICING.get(model, _Price(prompt=0.0, completion=0.0))
    return (prompt_tokens * price.prompt + completion_tokens * price.completion) / 1_000_000
