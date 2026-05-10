import inspect
import functools
from typing import get_type_hints, Callable

_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def tool(_fn: Callable = None, *, summarize_output: bool = True):
    def decorator(fn: Callable) -> Callable:
        hints = get_type_hints(fn)
        hints.pop("return", None)
        sig = inspect.signature(fn)

        properties = {
            "reason": {"type": "string", "description": "Your reason for calling this tool."},
            "summary": {"type": "string", "description": "One-line narration summary of what this tool call found or did. Be specific: include key values, filenames, counts, or outcomes — not just 'read file' or 'ran command'."},
        }
        required = ["reason", "summary"]

        for name, param in sig.parameters.items():
            if name in ("reason", "summary"):
                continue
            properties[name] = {"type": _TYPE_MAP.get(hints.get(name), "string")}
            if param.default is inspect.Parameter.empty:
                required.append(name)

        schema = {
            "type": "function",
            "function": {
                "name": fn.__name__,
                "description": fn.__doc__ or "",
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):
                kwargs.pop("reason", None)
                kwargs.pop("summary", None)
                return await fn(*args, **kwargs)
        else:
            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):
                kwargs.pop("reason", None)
                kwargs.pop("summary", None)
                return fn(*args, **kwargs)

        wrapper.schema = schema
        wrapper.summarize_output = summarize_output

        def bind(**locked):
            from nori.tools._bound import BoundTool
            return BoundTool(wrapper, locked)

        wrapper.bind = bind
        return wrapper

    if _fn is not None:
        return decorator(_fn)
    return decorator
