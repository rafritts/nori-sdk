import os
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
