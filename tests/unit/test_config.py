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


# ── Model validation ──────────────────────────────────────────────────────────

def test_model_empty_id_raises():
    with pytest.raises(ValueError, match="non-empty"):
        Model(id="", api_key="k")


def test_model_invalid_context_window():
    with pytest.raises(ValueError, match="context_window"):
        Model(id="x", api_key="k", context_window=0)


def test_model_negative_context_window():
    with pytest.raises(ValueError, match="context_window"):
        Model(id="x", api_key="k", context_window=-1)


def test_model_repr_with_provider():
    m = Model(id="gemma4:31b", provider=Provider.OLLAMA)
    r = repr(m)
    assert "gemma4:31b" in r
    assert "OLLAMA" in r


def test_model_repr_without_provider():
    m = Model(id="grok-4.3", api_key="sk-key")
    r = repr(m)
    assert "grok-4.3" in r


def test_model_http_client_without_base_url_raises():
    from unittest.mock import MagicMock
    with pytest.raises(ValueError, match="base_url"):
        Model(id="x", api_key="k", http_client=MagicMock())


def test_model_reasoning_effort_valid():
    m = Model(id="grok-4.3", api_key="k", reasoning_effort="low")
    assert m.reasoning_effort == "low"
    assert m.completion_kwargs() == {"model": "grok-4.3", "reasoning_effort": "low"}


def test_model_reasoning_effort_omitted_when_none():
    m = Model(id="grok-4.3", api_key="k")
    assert m.completion_kwargs() == {"model": "grok-4.3"}


def test_model_reasoning_effort_invalid_raises():
    with pytest.raises(ValueError, match="reasoning_effort"):
        Model(id="x", api_key="k", reasoning_effort="ultra")  # type: ignore[arg-type]


# ── server.py coverage ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ensure_started_early_return_if_already_running():
    from unittest.mock import AsyncMock, MagicMock, patch
    from nori import server as srv

    mock_task = MagicMock()
    orig = srv._server_task
    srv._server_task = mock_task
    try:
        from nori.config import ServerConfig
        cfg = ServerConfig(enabled=True, host="127.0.0.1", port=9999)
        # Should return immediately without starting a new server
        with patch("nori.server._make_app") as mock_app:
            await srv.ensure_started(cfg)
            mock_app.assert_not_called()
    finally:
        srv._server_task = orig


@pytest.mark.asyncio
async def test_server_shutdown_clears_state():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch
    from nori import server as srv

    orig_task = srv._server_task
    orig_server = srv._uvicorn_server

    mock_uv = MagicMock()

    # Create a real coroutine task that is already done
    async def _done():
        pass
    loop = asyncio.get_event_loop()
    done_task = loop.create_task(_done())
    await done_task  # let it complete

    srv._uvicorn_server = mock_uv
    srv._server_task = done_task

    try:
        await srv.shutdown()
        assert srv._server_task is None
        assert srv._uvicorn_server is None
    finally:
        srv._server_task = orig_task
        srv._uvicorn_server = orig_server
