"""
Integration tests — require real API credentials in .env or environment.
Run with: uv run pytest tests/integration/ -v
"""
import pytest

from nori import Agent
from nori.tool import tool


@pytest.mark.asyncio
async def test_single_completion():
    """Step 3 verify: single completion returns a non-empty string."""
    agent = Agent(name="Test", system_prompt="You are a helpful assistant.")
    result = await agent.run("Say hello.")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_tool_calling_loop():
    """Step 4 verify: agent calls a tool and returns a final response."""
    @tool
    def get_weather(city: str) -> str:
        """Get the current weather for a city."""
        return f"Sunny and 75°F in {city}."

    agent = Agent(
        name="WeatherAgent",
        system_prompt="You are a helpful assistant. Use tools when needed.",
        tools=[get_weather],
    )
    agent.summarize_tool_output = False

    result = await agent.run("What's the weather in Austin?")

    assert isinstance(result, str)
    assert len(result) > 0
    assert any(tc["name"] == "get_weather" for tc in agent.tool_calls)
