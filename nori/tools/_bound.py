import copy
import functools


class BoundTool:
    """A tool with specific parameters locked at bind time."""

    def __init__(self, tool_fn, locked: dict):
        self._fn = tool_fn
        self._locked = locked
        self._build_schema()

    def _build_schema(self):
        base = copy.deepcopy(self._fn.schema)
        props = base["function"]["parameters"]["properties"]
        required = base["function"]["parameters"]["required"]

        for key in self._locked:
            props.pop(key, None)
            if key in required:
                required.remove(key)

        self.schema = base
        self.summarize_output = getattr(self._fn, "summarize_output", True)

    async def __call__(self, **kwargs):
        kwargs.update(self._locked)
        return await self._fn(**kwargs)

    def __repr__(self):
        return f"BoundTool({self._fn.__name__}, locked={list(self._locked)})"
