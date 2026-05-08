from enum import Enum
from dataclasses import dataclass
from pathlib import Path


class ContextRole(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class ContextFile:
    path: str | Path
    role: ContextRole

    @property
    def content(self) -> str:
        return Path(self.path).read_text()
