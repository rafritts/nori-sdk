from pydantic import BaseModel


class ToolResult(BaseModel):
    result: str


class BaseTool:
    """Base class for class-based tools. Provides .bind() support."""

    @classmethod
    def bind(cls, **locked):
        """Return a bound version of this tool with locked params."""
        from nori.tools._bound import BoundTool
        return BoundTool(cls, locked)
