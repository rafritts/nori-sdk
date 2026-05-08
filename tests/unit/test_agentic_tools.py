from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def patch_sub_agent(result="sub-agent result"):
    """Patch Agent so any sub-agent instantiation returns a mock that returns `result`."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=result)
    return patch("nori.agent.Agent", return_value=mock_agent), mock_agent


# ── BashAgent ─────────────────────────────────────────────────────────────────

async def test_bash_agent_creates_sub_agent():
    with patch("nori.tools.bash_agent.Agent") as MockAgent:
        sub = MagicMock()
        sub.run = AsyncMock(return_value="done")
        MockAgent.return_value = sub
        from nori.tools.bash_agent import BashAgent
        await BashAgent(task="list files", reason="r")
        MockAgent.assert_called_once()


async def test_bash_agent_result_returned():
    with patch("nori.tools.bash_agent.Agent") as MockAgent:
        sub = MagicMock()
        sub.run = AsyncMock(return_value="ls output")
        MockAgent.return_value = sub
        from nori.tools.bash_agent import BashAgent
        result = await BashAgent(task="list files", reason="r")
        assert result == "ls output"


async def test_bash_agent_isolated_context():
    parent_history_before = []
    with patch("nori.tools.bash_agent.Agent") as MockAgent:
        sub = MagicMock()
        sub.run = AsyncMock(return_value="done")
        sub._history = []
        MockAgent.return_value = sub
        from nori.tools.bash_agent import BashAgent
        await BashAgent(task="do something", reason="r")
        # Sub-agent has its own history, not shared with parent
        assert sub._history == []


# ── FileEditAgent ─────────────────────────────────────────────────────────────

async def test_file_edit_agent_creates_sub_agent():
    with patch("nori.tools.file_edit_agent.Agent") as MockAgent:
        sub = MagicMock()
        sub.run = AsyncMock(return_value="done")
        MockAgent.return_value = sub
        from nori.tools.file_edit_agent import FileEditAgent
        await FileEditAgent(task="edit files", reason="r")
        MockAgent.assert_called_once()


async def test_file_edit_agent_result_returned():
    with patch("nori.tools.file_edit_agent.Agent") as MockAgent:
        sub = MagicMock()
        sub.run = AsyncMock(return_value="edits applied")
        MockAgent.return_value = sub
        from nori.tools.file_edit_agent import FileEditAgent
        result = await FileEditAgent(task="edit", reason="r")
        assert result == "edits applied"


# ── FileSearchAgent ───────────────────────────────────────────────────────────

async def test_file_search_agent_creates_sub_agent():
    with patch("nori.tools.file_search_agent.Agent") as MockAgent:
        sub = MagicMock()
        sub.run = AsyncMock(return_value="done")
        MockAgent.return_value = sub
        from nori.tools.file_search_agent import FileSearchAgent
        await FileSearchAgent(task="find files", reason="r")
        MockAgent.assert_called_once()


async def test_file_search_agent_result_returned():
    with patch("nori.tools.file_search_agent.Agent") as MockAgent:
        sub = MagicMock()
        sub.run = AsyncMock(return_value="found: foo.py")
        MockAgent.return_value = sub
        from nori.tools.file_search_agent import FileSearchAgent
        result = await FileSearchAgent(task="find", reason="r")
        assert result == "found: foo.py"


# ── WebAgent ──────────────────────────────────────────────────────────────────

async def test_web_agent_creates_sub_agent():
    with patch("nori.tools.web_agent.Agent") as MockAgent:
        sub = MagicMock()
        sub.run = AsyncMock(return_value="done")
        MockAgent.return_value = sub
        from nori.tools.web_agent import WebAgent
        await WebAgent(task="browse site", reason="r")
        MockAgent.assert_called_once()


async def test_web_agent_result_returned():
    with patch("nori.tools.web_agent.Agent") as MockAgent:
        sub = MagicMock()
        sub.run = AsyncMock(return_value="scraped content")
        MockAgent.return_value = sub
        from nori.tools.web_agent import WebAgent
        result = await WebAgent(task="scrape", reason="r")
        assert result == "scraped content"


# ── WebSearch ─────────────────────────────────────────────────────────────────

async def test_web_search_creates_sub_agent():
    with patch("nori.tools.web_search.Agent") as MockAgent:
        sub = MagicMock()
        sub.run = AsyncMock(return_value="done")
        MockAgent.return_value = sub
        from nori.tools.web_search import WebSearch
        await WebSearch(query="python asyncio", reason="r")
        MockAgent.assert_called_once()


async def test_web_search_result_returned():
    with patch("nori.tools.web_search.Agent") as MockAgent:
        sub = MagicMock()
        sub.run = AsyncMock(return_value="asyncio is a library")
        MockAgent.return_value = sub
        from nori.tools.web_search import WebSearch
        result = await WebSearch(query="python asyncio", reason="r")
        assert result == "asyncio is a library"


# ── CodeRunnerAgent ───────────────────────────────────────────────────────────

async def test_code_runner_agent_creates_sub_agent():
    with patch("nori.tools.code_runner_agent.Agent") as MockAgent:
        sub = MagicMock()
        sub.run = AsyncMock(return_value="done")
        MockAgent.return_value = sub
        from nori.tools.code_runner_agent import CodeRunnerAgent
        await CodeRunnerAgent(task="compute sum", reason="r")
        MockAgent.assert_called_once()


async def test_code_runner_agent_result_returned():
    with patch("nori.tools.code_runner_agent.Agent") as MockAgent:
        sub = MagicMock()
        sub.run = AsyncMock(return_value="result: 42")
        MockAgent.return_value = sub
        from nori.tools.code_runner_agent import CodeRunnerAgent
        result = await CodeRunnerAgent(task="compute", reason="r")
        assert result == "result: 42"
