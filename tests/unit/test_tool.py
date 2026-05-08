import pytest
from nori.tool import tool


@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return "sunny"


@tool
def compute(x: int, y: float, flag: bool, items: list, data: dict) -> str:
    """Multi-type function."""
    return ""


@tool(summarize_output=False)
def raw_output(path: str) -> str:
    """Returns raw output."""
    return ""


@tool
def with_default(city: str, units: str = "metric") -> str:
    """Has an optional param."""
    return ""


def _schema(fn):
    return fn.schema["function"]


def test_schema_name():
    assert _schema(get_weather)["name"] == "get_weather"


def test_schema_description():
    assert _schema(get_weather)["description"] == "Get the current weather for a city."


def test_reason_in_required():
    assert "reason" in _schema(get_weather)["parameters"]["required"]


def test_user_param_in_required():
    assert "city" in _schema(get_weather)["parameters"]["required"]


def test_reason_stripped_before_call():
    received = {}

    @tool
    def spy(city: str) -> str:
        """Spy."""
        received["kwargs"] = {"city": city}
        return city

    import asyncio
    asyncio.run(spy(city="Austin", reason="test reason"))
    assert "reason" not in received["kwargs"]


def test_type_mapping():
    props = _schema(compute)["parameters"]["properties"]
    assert props["x"]["type"] == "integer"
    assert props["y"]["type"] == "number"
    assert props["flag"]["type"] == "boolean"
    assert props["items"]["type"] == "array"
    assert props["data"]["type"] == "object"


def test_str_type_mapping():
    props = _schema(get_weather)["parameters"]["properties"]
    assert props["city"]["type"] == "string"


def test_summarize_output_default_true():
    assert get_weather.summarize_output is True


def test_summarize_output_flag_false():
    assert raw_output.summarize_output is False


def test_return_type_excluded_from_schema():
    props = _schema(get_weather)["parameters"]["properties"]
    assert "return" not in props


def test_optional_param_not_in_required():
    required = _schema(with_default)["parameters"]["required"]
    assert "units" not in required


def test_required_param_in_required():
    required = _schema(with_default)["parameters"]["required"]
    assert "city" in required


def test_async_function_wrapped():
    @tool
    async def async_tool(x: str) -> str:
        """Async tool."""
        return x

    import asyncio
    result = asyncio.run(async_tool(x="hello", reason="r"))
    assert result == "hello"
