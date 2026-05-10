"""Tests for Provider.BEDROCK and Model.http_client support."""
import sys
from unittest.mock import MagicMock, patch

import pytest

from nori import Model, Provider


# ── Bedrock model construction ────────────────────────────────────────────────

def _mock_boto3():
    """Patch boto3 and botocore with minimal mocks."""
    mock_boto3 = MagicMock()
    mock_creds = MagicMock()
    mock_boto3.Session.return_value.get_credentials.return_value = mock_creds

    mock_botocore_auth = MagicMock()
    mock_botocore_awsrequest = MagicMock()

    return {
        "boto3": mock_boto3,
        "botocore": MagicMock(),
        "botocore.auth": mock_botocore_auth,
        "botocore.awsrequest": mock_botocore_awsrequest,
    }


@pytest.fixture
def boto3_mocked(monkeypatch):
    mocks = _mock_boto3()
    for name, mock in mocks.items():
        monkeypatch.setitem(sys.modules, name, mock)
    # httpx is a real dep so we don't mock it
    yield mocks


def test_bedrock_sets_base_url_from_env(boto3_mocked, monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    m = Model(id="us.anthropic.claude-sonnet-4-5-20251001-v3:0", provider=Provider.BEDROCK)
    assert m.base_url == "https://bedrock-runtime.us-west-2.amazonaws.com/openai"


def test_bedrock_default_region_us_east_1(boto3_mocked, monkeypatch):
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    m = Model(id="us.anthropic.claude-sonnet-4-5-20251001-v3:0", provider=Provider.BEDROCK)
    assert m.base_url == "https://bedrock-runtime.us-east-1.amazonaws.com/openai"


def test_bedrock_explicit_region_wins(boto3_mocked, monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    m = Model(
        id="us.anthropic.claude-sonnet-4-5-20251001-v3:0",
        provider=Provider.BEDROCK,
        region="eu-west-1",
    )
    assert m.base_url == "https://bedrock-runtime.eu-west-1.amazonaws.com/openai"
    assert m.region == "eu-west-1"


def test_bedrock_sets_http_client(boto3_mocked):
    m = Model(id="us.anthropic.claude-sonnet-4-5-20251001-v3:0", provider=Provider.BEDROCK)
    assert m.http_client is not None


def test_bedrock_no_api_key_required(boto3_mocked):
    """Bedrock models should not raise even though api_key is not set."""
    m = Model(id="us.anthropic.claude-sonnet-4-5-20251001-v3:0", provider=Provider.BEDROCK)
    assert m.api_key is None


def test_bedrock_arn_model_id(boto3_mocked):
    """Application inference profile ARNs work as model IDs."""
    arn = "arn:aws:bedrock:us-east-1:123456789012:application-inference-profile/my-profile"
    m = Model(id=arn, provider=Provider.BEDROCK)
    assert m.id == arn


def test_bedrock_missing_boto3_raises(monkeypatch):
    monkeypatch.setitem(sys.modules, "boto3", None)
    with pytest.raises(ImportError, match="boto3 is required"):
        Model(id="us.anthropic.claude-sonnet-4-5-20251001-v3:0", provider=Provider.BEDROCK)


# ── http_client on non-Bedrock models ────────────────────────────────────────

def test_model_http_client_skips_api_key_validation():
    import httpx
    client = httpx.AsyncClient()
    m = Model(
        id="corp-model",
        base_url="https://llm.internal.corp.com/openai/v1",
        http_client=client,
    )
    assert m.http_client is client
    assert m.api_key is None


def test_model_http_client_no_base_url_raises():
    """http_client alone is not enough — base_url is still required."""
    import httpx
    with pytest.raises(ValueError):
        Model(id="corp-model", http_client=httpx.AsyncClient())


# ── Agent uses http_client ────────────────────────────────────────────────────

def test_agent_client_uses_http_client(boto3_mocked):
    from unittest.mock import patch as _patch
    from nori import Agent
    from openai import AsyncOpenAI

    m = Model(id="us.anthropic.claude-sonnet-4-5-20251001-v3:0", provider=Provider.BEDROCK)

    constructed_kwargs = {}

    original_init = AsyncOpenAI.__init__

    def capture_init(self, **kwargs):
        constructed_kwargs.update(kwargs)
        # Avoid actually connecting
        self._base_url = kwargs.get("base_url", "")
        self._api_key = kwargs.get("api_key", "")
        self._custom_headers = {}
        self._timeout = None
        self._max_retries = 2
        self._http_client = kwargs.get("http_client")
        self.__httpx_client = kwargs.get("http_client")

    with _patch.object(AsyncOpenAI, "__init__", capture_init):
        agent = Agent(name="T", model=m)
        _ = agent._client

    assert constructed_kwargs.get("http_client") is m.http_client
    assert constructed_kwargs.get("api_key") == "nori"
