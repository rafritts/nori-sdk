from enum import Enum, IntEnum


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
