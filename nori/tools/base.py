class BaseTool:
    """Base class for class-based tools. Provides .bind() support (Step 24)."""

    @classmethod
    def bind(cls, **locked):
        """Return a bound version of this tool with locked params."""
        from nori.tools._bound import BoundTool
        return BoundTool(cls, locked)
