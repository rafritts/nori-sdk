from dataclasses import dataclass, field


@dataclass
class MCPServer:
    name: str
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""

    def __post_init__(self):
        if not self.command and not self.url:
            raise ValueError("MCPServer requires either 'command' (stdio) or 'url' (HTTP/SSE).")
