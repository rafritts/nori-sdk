import importlib
import os

import pytest

import nori.config as config_module
from nori import Agent


def test_default_model_fallback(monkeypatch):
    monkeypatch.delenv("NORI_MODEL", raising=False)
    importlib.reload(config_module)
    assert config_module.DEFAULT_MODEL == "grok-4.3"


def test_default_model_from_env(monkeypatch):
    monkeypatch.setenv("NORI_MODEL", "gpt-5")
    importlib.reload(config_module)
    assert config_module.DEFAULT_MODEL == "gpt-5"


def test_api_key_from_env(monkeypatch):
    monkeypatch.setenv("NORI_API_KEY", "sk-test-123")
    importlib.reload(config_module)
    assert config_module.API_KEY == "sk-test-123"


def test_base_url_from_env(monkeypatch):
    monkeypatch.setenv("NORI_BASE_URL", "https://api.example.com")
    importlib.reload(config_module)
    assert config_module.BASE_URL == "https://api.example.com"


def test_agent_uses_config_model(monkeypatch):
    monkeypatch.setattr(config_module, "DEFAULT_MODEL", "grok-ultra")
    agent = Agent(name="T")
    assert agent.model == "grok-ultra"


def test_agent_explicit_model_overrides_config(monkeypatch):
    monkeypatch.setattr(config_module, "DEFAULT_MODEL", "grok-ultra")
    agent = Agent(name="T", model="gpt-4o")
    assert agent.model == "gpt-4o"


def test_agent_uses_config_api_key(monkeypatch):
    monkeypatch.setattr(config_module, "API_KEY", "sk-from-config")
    agent = Agent(name="T")
    assert agent._api_key == "sk-from-config"


def test_agent_explicit_api_key_overrides_config(monkeypatch):
    monkeypatch.setattr(config_module, "API_KEY", "sk-from-config")
    agent = Agent(name="T", api_key="sk-explicit")
    assert agent._api_key == "sk-explicit"


def test_agent_uses_config_base_url(monkeypatch):
    monkeypatch.setattr(config_module, "BASE_URL", "https://custom.api")
    agent = Agent(name="T")
    assert agent._base_url == "https://custom.api"
