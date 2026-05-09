"""
Demonstrates the @tool decorator.

@tool introspects a function's name, docstring, and type annotations to build
an OpenAI-compatible schema. It automatically injects 'reason' as a required
parameter (so the agent must state why it's calling the tool) and strips it
before invoking the underlying function.

Shows:
  1. Basic @tool — schema generation, reason injection, type mapping
  2. @tool(summarize_output=False) — opt out of LLM summarization
  3. Async tools — @tool works on coroutines too
  4. .bind() — lock parameters to fixed values, creating a restricted variant
  5. All of the above wired into a real agent run
"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json

from nori import Agent
from nori.tool import tool

DIVIDER = "=" * 60


def section(title: str) -> None:
    print(f"\n{DIVIDER}")
    print(title)
    print(DIVIDER)


# ── 1. Basic @tool ────────────────────────────────────────────────────────────

@tool
def get_weather(city: str, unit: str = "celsius") -> str:
    """Get the current weather for a city."""
    return f"Sunny, 22°{'C' if unit == 'celsius' else 'F'} in {city}."


section("1. Basic @tool — generated schema")
print(json.dumps(get_weather.schema, indent=2))

print(f"\nreason in required: {'reason' in get_weather.schema['function']['parameters']['required']}")
print(f"city in required:   {'city' in get_weather.schema['function']['parameters']['required']}")
print(f"summarize_output:   {get_weather.summarize_output}")


# ── 2. summarize_output=False ─────────────────────────────────────────────────

@tool(summarize_output=False)
def get_raw_metrics(host: str) -> str:
    """Return raw system metrics for a host. Output should not be summarized."""
    return f"cpu=12% mem=44% disk=71% host={host}"


section("2. @tool(summarize_output=False)")
print(f"summarize_output: {get_raw_metrics.summarize_output}")
print(f"Schema: {json.dumps(get_raw_metrics.schema['function']['parameters']['properties'], indent=2)}")


# ── 3. Async tool ─────────────────────────────────────────────────────────────

@tool
async def fetch_price(ticker: str) -> str:
    """Fetch the current stock price for a ticker symbol."""
    await asyncio.sleep(0)  # simulated async I/O
    prices = {"AAPL": 213.49, "GOOG": 178.02, "MSFT": 415.33}
    price = prices.get(ticker.upper(), 0.0)
    return f"{ticker.upper()}: ${price:.2f}"


section("3. Async @tool")
print(f"Schema name: {fetch_price.schema['function']['name']}")
print(f"Is coroutine function: {asyncio.iscoroutinefunction(fetch_price)}")


# ── 4. .bind() — locked parameters ───────────────────────────────────────────

section("4. .bind() — lock parameters to fixed values")

get_london_weather = get_weather.bind(city="London", unit="celsius")
print(f"Original schema params: {list(get_weather.schema['function']['parameters']['properties'].keys())}")
print(f"Bound schema params:    {list(get_london_weather.schema['function']['parameters']['properties'].keys())}")
print(f"\nCalling bound tool (city and unit are locked):")
result = asyncio.run(get_london_weather(reason="demo"))
print(f"  → {result}")


# ── 5. Real agent run ─────────────────────────────────────────────────────────

async def run_agent():
    section("5. All tools wired into a real agent run")

    # Bind a city-specific weather tool so the agent can't pick a different city
    get_tokyo_weather = get_weather.bind(city="Tokyo")

    agent = Agent(
        name="ToolDemoAgent",
        system_prompt="You are a helpful assistant with access to weather, metrics, and stock tools.",
        tools=[get_tokyo_weather, get_raw_metrics, fetch_price],
    )
    agent.summarize_tool_output = False
    agent.narration = True

    result = await agent.run(
        "What's the weather in Tokyo? Also grab metrics for host 'prod-1' "
        "and get me the price of AAPL and MSFT."
    )
    print(f"Agent: {result}")
    print(f"\nTurns: {agent.turn_count}  |  Cost: ${agent.cost:.4f}")


asyncio.run(run_agent())
