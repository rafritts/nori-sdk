import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nori import Agent, Model, Permissions
from nori.exceptions import PermissionError
from nori.permissions import PermissionGuard
from nori.tool import tool


@tool
def bash_tool(command: str) -> str:
    """Bash."""
    return "ok"


@tool
def bash_agent_tool(command: str) -> str:
    """BashAgent."""
    return "ok"


@tool
def file_edit_tool(path: str) -> str:
    """FileEdit."""
    return "ok"


def make_tool_call_message(name, args=None, call_id="c1"):
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(args or {"reason": "r"})
    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tc]
    return msg


def make_text_message(content="Done."):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    return msg


def test_allow_and_deny_raises_at_construction():
    with pytest.raises((RuntimeError, ValueError)):
        Agent(name="T", model=Model(id="grok-4.3", api_key="test-key"), permissions=Permissions(allow=["bash"], deny=["file_edit"]))


def test_denied_tool_raises_permission_error():
    guard = PermissionGuard(allow=None, deny=["bash_tool"])
    with pytest.raises(PermissionError):
        guard.check("bash_tool")


def test_allowed_tool_passes():
    guard = PermissionGuard(allow=["bash_tool"], deny=None)
    guard.check("bash_tool")  # should not raise


def test_unlisted_tool_blocked_by_allow():
    guard = PermissionGuard(allow=["bash_tool"], deny=None)
    with pytest.raises(PermissionError):
        guard.check("file_edit_tool")


def test_glob_deny():
    guard = PermissionGuard(allow=None, deny=["bash*"])
    with pytest.raises(PermissionError):
        guard.check("bash_tool")
    with pytest.raises(PermissionError):
        guard.check("bash_agent_tool")


def test_glob_allow():
    guard = PermissionGuard(allow=["file*"], deny=None)
    guard.check("file_edit_tool")  # should pass
    with pytest.raises(PermissionError):
        guard.check("bash_tool")


async def test_denied_tool_raises_in_agent_loop():
    with patch("nori.agent.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=[
            MagicMock(choices=[MagicMock(message=make_tool_call_message(
                "bash_tool", {"command": "ls", "reason": "r"}
            ))]),
            MagicMock(choices=[MagicMock(message=make_text_message())]),
        ])
        MockOpenAI.return_value = mock_client

        agent = Agent(
            name="T", model=Model(id="grok-4.3", api_key="test-key"),
            tools=[bash_tool],
            permissions=Permissions(deny=["bash_tool"]),
        )
        with pytest.raises(PermissionError):
            await agent.run("go")
