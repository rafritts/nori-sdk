import pytest

from nori import Agent, Model


def test_agent_explicit_api_key():
    agent = Agent(name="T", model=Model(id="grok-4.3", api_key="sk-explicit"))
    assert agent._model.api_key == "sk-explicit"


def test_agent_base_url():
    agent = Agent(name="T", model=Model(id="grok-4.3", base_url="https://custom.api"))
    assert agent._model.base_url == "https://custom.api"
