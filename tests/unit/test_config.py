import pytest

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
