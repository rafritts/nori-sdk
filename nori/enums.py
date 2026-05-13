from enum import Enum, IntEnum, StrEnum  # noqa: F401



class ResizeMode(IntEnum):
    NONE       = 0     # no resize
    AGGRESSIVE = 512   # logos, icons, small UI elements
    MODERATE   = 1024  # default — good for most photos and diagrams
    LIGHT      = 2048  # documents, charts where fine text matters


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


class Propagation(Enum):
    ALWAYS        = "always"        # sub-agents always inherit the scratchpad
    NEVER         = "never"         # scratchpad is private to this agent
    DISCRETIONARY = "discretionary" # agent decides at runtime via ScratchpadPropagate


class ScratchpadUsage(Enum):
    REQUIRED  = "required"   # treat scratchpad as mandatory — read/write before producing output
    SELECTIVE = "selective"  # write only critical information; do not clutter with noise


class OutputFormat(Enum):
    TEXT             = "text"
    OPENAI_CHAT      = "openai_chat"
    OPENAI_RESPONSES = "openai_responses"
