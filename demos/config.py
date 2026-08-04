import nori
from nori import Model, Provider
from nori.tools.file_search_agent import FileSearchAgent

_main = Model(id="grok-4.5", provider=Provider.XAI)
_fast = Model(id="grok-4-1-fast-reasoning", provider=Provider.XAI)

nori.configure(
    model=_main,
    tool_models={FileSearchAgent: _fast},
)

# Convenience exports for demos that need to override the default.
MAIN_MODEL = _main
FAST_MODEL = _fast
