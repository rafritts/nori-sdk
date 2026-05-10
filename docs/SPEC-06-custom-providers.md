# SPEC-06: Custom Providers and AWS Bedrock

## Problem

Every provider in Nori today uses the same auth path: `AsyncOpenAI(api_key="...", base_url="...")`.
Two cases break this assumption:

1. **AWS Bedrock** — uses AWS Signature V4. No static API key; credentials come from IAM roles,
   `~/.aws/credentials`, env vars, or instance metadata. Base URL is region-dependent.
2. **Corporate / arbitrary endpoints** — custom auth headers, OAuth tokens, mTLS, proprietary
   signing. No way to express these through `api_key=` alone.

---

## Design principle

**Setup has one deliberate step. Everything after is identical.**

A corporate Bedrock user's `config.py`:

```python
import nori
from nori import Model, Provider

nori.configure(
    model=Model(id="us.anthropic.claude-sonnet-4-5-20251001-v3:0", provider=Provider.BEDROCK),
)
```

After that, they use `Agent(name=..., tools=[...])` exactly like any other provider.
The only Bedrock-specific friction is: picking the right model ID and having AWS credentials
configured in their environment (which corporate users already have).

---

## Solution

Two additions:

1. **`Provider.BEDROCK`** — first-class enum entry. `Model.__post_init__` detects it and handles
   the SigV4 setup automatically. Optional `region` field on `Model` for override; defaults to
   `AWS_DEFAULT_REGION` env var, then `us-east-1`.

2. **`Model.http_client`** — escape hatch for truly custom auth flows (corporate SSO, mTLS, etc.).
   When set, `Agent._client` uses it directly and skips all default auth.

---

## API

### `Provider.BEDROCK`

Added to the `Provider` enum. Unlike other entries, `base_url` and `api_key` are placeholders —
the real setup happens in `Model.__post_init__`.

```python
Provider.BEDROCK = ("__bedrock__", None)  # sentinel; real URL built from region at model init
```

### `Model` changes

```python
@dataclass
class Model:
    id: str
    api_key: str | None = None
    base_url: str | None = None
    context_window: int = ContextWindow.M1
    provider: Provider | None = None
    region: str | None = None        # NEW: used by Provider.BEDROCK; ignored by all others
    http_client: object | None = None  # NEW: custom httpx.AsyncClient, bypasses all auth
```

`__post_init__` behaviour when `provider=Provider.BEDROCK`:
- Resolves region: `self.region` → `AWS_DEFAULT_REGION` env var → `"us-east-1"`
- Sets `base_url` to `https://bedrock-runtime.{region}.amazonaws.com/openai`
- Builds an `httpx.AsyncClient` with SigV4 auth using `boto3` and assigns it to `self.http_client`
- Skips the `api_key` / `base_url` presence check (http_client is sufficient)

Raises `ImportError` with a clear message if `boto3` is not installed.

### `Agent._client` change

```python
@property
def _client(self) -> AsyncOpenAI:
    if self.__client is None:
        if self._model.http_client is not None:
            self.__client = AsyncOpenAI(
                http_client=self._model.http_client,
                base_url=self._model.base_url,
                api_key="nori",  # SDK requires non-empty; ignored when http_client is provided
            )
        else:
            self.__client = AsyncOpenAI(
                api_key=self._model.api_key,
                base_url=self._model.base_url,
            )
    return self.__client
```

### Custom endpoint pattern (corporate escape hatch)

For endpoints that can't be expressed through `Provider.BEDROCK` or any other enum entry:

```python
import httpx
from nori import Agent, Model

class CorpAuth(httpx.Auth):
    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {fetch_token()}"
        yield request

model = Model(
    id="corp-model-id",
    base_url="https://llm.internal.corp.com/openai/v1",
    http_client=httpx.AsyncClient(auth=CorpAuth(), verify="/etc/ssl/corp-ca.pem"),
)
```

This is intentionally a lower-level API. It's the escape hatch, not the happy path.

---

## Implementation plan

### 1. `nori/providers.py`

Add `BEDROCK = ("__bedrock__", None)` to the `Provider` enum.

The `base_url` property for BEDROCK returns the sentinel string — `Model.__post_init__`
overwrites it with the real region-qualified URL.

### 2. `nori/providers/bedrock.py` (new file)

```python
def _make_bedrock_client(region: str) -> "httpx.AsyncClient":
    """Build an httpx.AsyncClient that signs requests with AWS SigV4."""
    try:
        import boto3
        import botocore.auth
        import botocore.awsrequest
        import httpx
    except ImportError:
        raise ImportError(
            "boto3 is required for Provider.BEDROCK. "
            "Install it with: uv add boto3"
        )

    class _SigV4Auth(httpx.Auth):
        def __init__(self, session, region):
            self._creds = session.get_credentials()
            self._region = region

        def auth_flow(self, request):
            creds = self._creds.get_frozen_credentials()
            aws_req = botocore.awsrequest.AWSRequest(
                method=request.method,
                url=str(request.url),
                data=request.content,
                headers=dict(request.headers),
            )
            botocore.auth.SigV4Auth(creds, "bedrock", self._region).add_auth(aws_req)
            for k, v in aws_req.headers.items():
                request.headers[k] = v
            yield request

    session = boto3.Session()
    return httpx.AsyncClient(auth=_SigV4Auth(session, region))
```

### 3. `nori/model.py`

- Add `region: str | None = None` and `http_client: object | None = None` fields
- In `__post_init__`, detect `Provider.BEDROCK` and call `_make_bedrock_client`
- Adjust the validation check: skip api_key/base_url requirement when `http_client` is set

### 4. `nori/agent.py`

Update `_client` property to branch on `self._model.http_client` as shown above.

### 5. `pyproject.toml`

```toml
[project.optional-dependencies]
bedrock = ["boto3"]
```

### 6. Pricing

Bedrock billing is per-model and goes directly to AWS. `cost_for()` returns `0.0` for Bedrock
model IDs — same treatment as Ollama and OpenRouter. Document this clearly: agent.cost will
be $0.00 for Bedrock runs; check the AWS console for actual spend.

### 7. Tests

- `test_model_bedrock_sets_base_url` — mocked boto3, verify base_url is region-qualified
- `test_model_bedrock_sets_http_client` — verify http_client is populated
- `test_model_bedrock_explicit_region_wins` — `region="eu-west-1"` overrides env var
- `test_model_bedrock_missing_boto3_raises` — mock ImportError, verify helpful message
- `test_model_http_client_skips_api_key_validation` — model with http_client but no api_key is valid
- `test_agent_client_uses_http_client` — AsyncOpenAI constructed with http_client when set

---

## Open questions

- **Client lifecycle**: Nori does not close a user-supplied `http_client`. The Bedrock client
  (created internally) also isn't closed explicitly — acceptable given asyncio cleanup semantics
  and the fact that agents are typically short-lived.
- **Bedrock model IDs**: Long and version-pinned (`us.anthropic.claude-sonnet-4-5-20251001-v3:0`).
  No aliasing planned — corporate users know their model IDs, and aliasing would rot quickly as
  Bedrock adds versions. Document common IDs in a README or example config.
- **Cross-region inference**: Bedrock's `us.*` prefix model IDs enable cross-region inference.
  No special handling needed — it's just part of the model ID string.
