from enum import Enum, IntEnum, StrEnum


class BaseURL(StrEnum):
    OPENAI      = "https://api.openai.com/v1"
    ANTHROPIC   = "https://api.anthropic.com/v1"
    XAI         = "https://api.x.ai/v1"
    GROQ        = "https://api.groq.com/openai/v1"
    MISTRAL     = "https://api.mistral.ai/v1"
    TOGETHER    = "https://api.together.xyz/v1"
    FIREWORKS   = "https://api.fireworks.ai/inference/v1"
    DEEPSEEK    = "https://api.deepseek.com/v1"
    CEREBRAS    = "https://api.cerebras.ai/v1"
    PERPLEXITY  = "https://api.perplexity.ai"
    GOOGLE      = "https://generativelanguage.googleapis.com/v1beta/openai/"
    OPENROUTER  = "https://openrouter.ai/api/v1"
    OLLAMA      = "http://localhost:11434/v1"


class ContextWindow(IntEnum):
    K24   =    24_000
    K32   =    32_000
    K128  =   128_000
    K200  =   200_000
    M1    = 1_000_000


class ContextRole(Enum):
    SYSTEM    = "system"
    USER      = "user"
    ASSISTANT = "assistant"


class CheckpointScrutiny(Enum):
    STRICT   = "strict"
    MODERATE = "moderate"
    LENIENT  = "lenient"


class SelfModify(Enum):
    CUSTODIAN = "custodian"   # read/inspect agent state only
    MODIFY    = "modify"      # edit tools and config; implies CUSTODIAN
    MUTATION  = "mutation"    # full self-rewrite; implies MODIFY and CUSTODIAN
