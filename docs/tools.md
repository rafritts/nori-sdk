# Tools

## Built-in tool library

Nori ships with tools for the most common agent tasks. Many tools have both a **native** version (single call, direct result) and an **agentic** version (runs a sub-agent with its own context window, returns a summarized result — useful when the output would be too large to fit in the main context).

| Tool | Agentic version | Description |
|---|---|---|
| `Bash` | `BashAgent` | Execute shell commands |
| `FileRead` | `FileReadAgent` | Read files from disk |
| `FileWrite` | `FileWriteAgent` | Write files to disk |
| `FileEdit` | `FileEditAgent` | Edit files with search/replace |
| `FileSearch` | `FileSearchAgent` | Search files by content or name |
| `Git` | `GitAgent` | Run git operations |
| `JsonRead` | `JsonReadAgent` | Read and query JSON files |
| `CsvRead` | `CsvReadAgent` | Read and query CSV files |
| `WebSearch` | `WebAgent` | Search the web |
| `WebClient` | — | Fetch and parse web pages |
| `ApiClient` | — | Make HTTP API calls |
| `BrowserClient` | — | One-shot Playwright page fetch/extract |
| `BrowserAgent` | — | Multi-step browser agent |
| `CodeRunner` | `CodeRunnerAgent` | Execute Python code in isolation |
| `ViewImage` | — | View images (for vision-capable models) |
| `Postgres` | `PostgresAgent` | Query a Postgres database |
| `Redis` | `RedisAgent` | Read and write Redis keys |
| `Mongo` | `MongoAgent` | Query a MongoDB collection |
| `HumanInput` | — | Pause and ask a human for input (requires server) |
| `Notify` | — | Send a notification (Slack, webhook) |
| `ScratchpadRead` | — | Read from a shared scratchpad |
| `ScratchpadWrite` | — | Write to a shared scratchpad |
| `Compact` | — | Voluntarily compact conversation history |

Browser tools need the `browser` extra. Database tools need their respective extras (`postgres`, `redis`, `mongo`). `HumanInput` needs the `server` extra and `nori.configure(server=True)`.

Import from the specific module (recommended) or from `nori.tools` for the subset re-exported there:

```python
from nori.tools.bash import Bash
from nori.tools.file_read import FileRead
from nori.tools.browser import BrowserClient, BrowserAgent
from nori.tools.compact import Compact
from nori.tools import Git, HumanInput, Notify  # partial re-exports
```

Tool schema **names** match the class/function names above (`Bash`, `FileRead`, …). Use those exact names in `Permissions` allow/deny lists.

---

## The `@tool` decorator

`@tool` turns any function into a Nori-compatible tool. It reads the function's name, docstring, and type annotations to build the OpenAI tool schema automatically. It also injects:

- **`reason`** (required) — why the model is calling the tool
- **`summary`** (required) — one-line narration of what the call found or did
- **`update_for_user`** (optional) — one-sentence status for the user while the tool runs

```python
from nori.tool import tool

@tool
def get_weather(city: str, unit: str = "celsius") -> str:
    """Get the current weather for a city."""
    return f"Sunny, 22°C in {city}."
```

That's all you need. Pass it to `tools=` on any agent.

### Async tools

`@tool` works on coroutines too:

```python
@tool
async def fetch_price(ticker: str) -> str:
    """Fetch the current stock price for a ticker symbol."""
    price = await some_api_call(ticker)
    return f"{ticker}: ${price:.2f}"
```

### Opting out of summarization

By default, tool output can be summarized by Nori to keep context lean. If your tool returns data the agent must read exactly (raw metrics, structured JSON, etc.), opt out:

```python
@tool(summarize_output=False)
def get_raw_metrics(host: str) -> str:
    """Return raw system metrics for a host."""
    return f"cpu=12% mem=44% disk=71% host={host}"
```

---

## Bound tools

`.bind()` locks one or more parameters to fixed values and returns a new tool. The locked parameters are removed from the schema entirely — the model never sees them and can't override them.

```python
get_london_weather = get_weather.bind(city="London", unit="celsius")

agent = Agent(
    name="LondonAgent",
    system_prompt="You report London weather.",
    tools=[get_london_weather],
)
```

Useful for creating scoped, restricted tool variants from a general-purpose tool.

---

## Compact

`Compact` is a normal tool you opt into by adding it to `tools=`. When called, the agent loop intercepts it and runs the same compaction path as the 85% autocompact threshold.

```python
from nori.tools.compact import Compact

agent = Agent(
    name="LongRunner",
    tools=[Bash, Compact],
)
```

Autocompaction at 85% fill always runs whether or not `Compact` is registered.

---

## Full example

See [`tool_decorator_demo.py`](https://github.com/rafritts/nori-sdk/blob/master/demos/tool_decorator_demo.py) for a complete walkthrough: schema generation, async tools, `summarize_output=False`, `.bind()`, and all of it wired into a real agent run.
