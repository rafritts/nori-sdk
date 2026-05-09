import nori
from nori import Model, Provider

_main = Model(id="grok-4.3", provider=Provider.XAI)
_fast = Model(id="grok-4-1-fast-reasoning", provider=Provider.XAI)

nori.configure(
    model=_main,
    tool_models={},  # populated as tools expose model= attributes
)

# Convenience exports for demos that need to override the default.
MAIN_MODEL = _main
FAST_MODEL = _fast
