"""
Integration tests — run against the XAI API (grok-4.3).
Run with: uv run pytest tests/integration/ -v
Requires XAI_API_KEY in the environment.
"""
import pytest

import config
from nori import Agent
from nori.tool import tool


@pytest.mark.asyncio
async def test_single_completion():
    """Single completion returns a non-empty string."""
    agent = Agent(name="Test", model=config.MAIN_MODEL, system_prompt="You are a helpful assistant.")
    result = await agent.run("Say hello.")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_tool_calling_loop():
    """Agent calls a tool and returns a final response."""
    @tool
    def get_weather(city: str) -> str:
        """Get the current weather for a city."""
        return f"Sunny and 75°F in {city}."

    agent = Agent(
        name="WeatherAgent",
        model=config.MAIN_MODEL,
        system_prompt="You are a helpful assistant. Use tools when needed.",
        tools=[get_weather],
    )

    result = await agent.run("What's the weather in Austin?")

    assert isinstance(result, str)
    assert len(result) > 0
    assert any(tc["name"] == "get_weather" for tc in agent.tool_calls)
