from dataclasses import dataclass


@dataclass(frozen=True)
class _Price:
    prompt: float   # $ per 1M tokens
    completion: float


_TABLE: dict[str, _Price] = {
    "grok-4.3":          _Price(prompt=5.00,  completion=15.00),
    "grok-3":            _Price(prompt=3.00,  completion=15.00),
    "grok-3-mini":       _Price(prompt=0.30,  completion=0.50),
    "gpt-4o":            _Price(prompt=2.50,  completion=10.00),
    "gpt-4o-mini":       _Price(prompt=0.15,  completion=0.60),
    "claude-sonnet-4-6": _Price(prompt=3.00,  completion=15.00),
    "claude-opus-4-7":   _Price(prompt=15.00, completion=75.00),
    "claude-haiku-4-5":  _Price(prompt=0.80,  completion=4.00),
}


def cost_for(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    price = _TABLE.get(model, _Price(prompt=0.0, completion=0.0))
    return (prompt_tokens * price.prompt + completion_tokens * price.completion) / 1_000_000
