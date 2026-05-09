import pytest

import nori
from nori import Agent, Model, Provider


def test_agent_explicit_api_key():
    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="sk-explicit"))
    assert agent._model.api_key == "sk-explicit"


def test_agent_base_url():
    agent = Agent(name="T", model=Model(id="grok-4.3", base_url="https://custom.api"))
    assert agent._model.base_url == "https://custom.api"


def test_model_provider_fills_base_url():
    m = Model(id="gemma4:31b", provider=Provider.OLLAMA)
    assert m.base_url == Provider.OLLAMA.base_url


def test_model_provider_fills_api_key():
    m = Model(id="gemma4:31b", provider=Provider.OLLAMA)
    assert m.api_key == Provider.OLLAMA.api_key


def test_model_explicit_fields_override_provider():
    m = Model(id="x", provider=Provider.OLLAMA, base_url="https://override.local")
    assert m.base_url == "https://override.local"


def test_model_missing_all_raises():
    with pytest.raises(ValueError):
        Model(id="x")


# ── nori.configure() / nori.reset() ──────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_config():
    yield
    nori.reset()


def _model(id="test-model"):
    return Model(id=id, api_key="test-key")


def test_configure_sets_model_default():
    nori.configure(model=_model())
    agent = Agent(name="T")
    assert agent.model == "test-model"


def test_agent_model_wins_over_configure():
    nori.configure(model=_model("global"))
    agent = Agent(name="T", model=_model("explicit"))
    assert agent.model == "explicit"


def test_configure_sets_timeout_defaults():
    nori.configure(model=_model(), tool_timeout=5.0, run_timeout=60.0)
    agent = Agent(name="T")
    assert agent.tool_timeout == 5.0
    assert agent.run_timeout == 60.0


def test_agent_timeout_wins_over_configure():
    nori.configure(model=_model(), tool_timeout=5.0, run_timeout=60.0)
    agent = Agent(name="T", tool_timeout=1.0, run_timeout=10.0)
    assert agent.tool_timeout == 1.0
    assert agent.run_timeout == 10.0


def test_configure_sets_max_turns():
    nori.configure(model=_model(), max_turns=42)
    agent = Agent(name="T")
    assert agent._max_turns == 42


def test_reset_clears_defaults():
    nori.configure(model=_model())
    nori.reset()
    with pytest.raises(ValueError, match="requires a model"):
        Agent(name="T")


def test_configure_merges_tool_models():
    class FakeTool:
        pass

    class OtherTool:
        pass

    m1 = _model("m1")
    m2 = _model("m2")
    nori.configure(model=_model(), tool_models={FakeTool: m1})
    nori.configure(tool_models={OtherTool: m2})
    from nori.config import get_defaults
    d = get_defaults()
    assert d.tool_models[FakeTool] is m1
    assert d.tool_models[OtherTool] is m2
