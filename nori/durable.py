"""Crash-safe journal for agent runs.

Every run is snapshotted to SQLite (WAL, synchronous=FULL) before each model
call and around each tool call. A process kill loses only the in-flight step.
Resume with the same run id.

Tools are at-least-once. A tool whose result was committed is not repeated.
A tool that had started but not committed runs again. Give side-effecting tools
idempotent arguments if a repeated call would be harmful.

HITL answers are committed before the waiting agent observes them, and the
request id is stable, so a kill during the wait does not lose a response that
already landed and does not mint a new question.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import nori.config as config

logger = logging.getLogger("nori.durable")

_run_id_var: ContextVar[str | None] = ContextVar("nori_run_id", default=None)
_tool_call_id_var: ContextVar[str | None] = ContextVar("nori_tool_call_id", default=None)
# Shared mutable counter so parallel tasks spawned from one tool call allocate
# distinct child run ids. ContextVar copies are shallow, so the dict is shared.
_child_counts_var: ContextVar[dict | None] = ContextVar("nori_child_counts", default=None)

_journal: Journal | None = None
_journal_path: str | None = None


def current_run_id() -> str | None:
    return _run_id_var.get()


def current_tool_call_id() -> str | None:
    return _tool_call_id_var.get()


def bind_run(run_id: str | None):
    return _run_id_var.set(run_id)


def unbind_run(token) -> None:
    _run_id_var.reset(token)


def bind_tool_call(tool_call_id: str):
    return (
        _tool_call_id_var.set(tool_call_id),
        _child_counts_var.set({}),
    )


def unbind_tool_call(tokens) -> None:
    tool_token, counts_token = tokens
    _tool_call_id_var.reset(tool_token)
    _child_counts_var.reset(counts_token)


def allocate_child_run_id() -> str | None:
    """Stable id for an agent run started inside the current tool call.

    The first nested run uses ``{parent}/{tool_call_id}``. Later ones in the
    same call append ``#n``. Re-executing the tool allocates the same ids in
    the same order, so finished children return their stored result.
    """
    parent = _run_id_var.get()
    tool = _tool_call_id_var.get()
    counts = _child_counts_var.get()
    if not parent or not tool or counts is None:
        return None
    n = counts.get(tool, 0)
    counts[tool] = n + 1
    if n == 0:
        return f"{parent}/{tool}"
    return f"{parent}/{tool}#{n}"


def resolve_path(cfg=None) -> str:
    cfg = cfg if cfg is not None else config.get_defaults().durable
    if cfg.path:
        return cfg.path
    env = os.environ.get("NORI_STATE_PATH")
    if env:
        return env
    return str(Path.home() / ".nori" / "runs.db")


def get_journal() -> Journal | None:
    global _journal, _journal_path
    cfg = config.get_defaults().durable
    if not cfg.enabled:
        return None
    path = resolve_path(cfg)
    if _journal is not None and _journal_path == path:
        return _journal
    if _journal is not None:
        _journal.close()
    _journal = Journal(path)
    _journal_path = path
    logger.debug("durable journal %s", path)
    return _journal


def close_journal() -> None:
    global _journal, _journal_path
    if _journal is not None:
        _journal.close()
    _journal = None
    _journal_path = None


def list_runs(status: str | None = None) -> list[dict]:
    """Summaries of journaled runs. Empty when durability is off."""
    journal = get_journal()
    if journal is None:
        return []
    return journal.list_runs(status)


def raise_stored(error_type: str | None, message: str | None) -> None:
    from nori.exceptions import AntiSpinTerminated, MaxTurnsExceeded

    text = message or "run failed"
    cls = {
        "MaxTurnsExceeded": MaxTurnsExceeded,
        "AntiSpinTerminated": AntiSpinTerminated,
    }.get(error_type or "")
    if cls is None:
        prefix = f"{error_type}: " if error_type else ""
        raise RuntimeError(f"{prefix}{text}")
    raise cls(text)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Journal:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._con = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._con.row_factory = sqlite3.Row
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute("PRAGMA synchronous=FULL")
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                agent_name TEXT NOT NULL,
                status TEXT NOT NULL,
                prompt TEXT,
                result TEXT,
                error_type TEXT,
                error TEXT,
                state_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS hitl (
                request_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                tool_call_id TEXT NOT NULL,
                agent_name TEXT,
                question TEXT,
                options_json TEXT,
                response TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(run_id, tool_call_id)
            )
            """
        )

    def close(self) -> None:
        self._con.close()

    def get_run(self, run_id: str) -> dict | None:
        with self._lock:
            row = self._con.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["state"] = json.loads(data.pop("state_json"))
        return data

    def save_run(
        self,
        run_id: str,
        *,
        agent_name: str,
        status: str,
        prompt: str | None,
        result: str | None,
        error_type: str | None,
        error: str | None,
        state: dict,
    ) -> None:
        if status == "running" and self.has_open_hitl(run_id):
            status = "waiting"
        payload = json.dumps(state, ensure_ascii=False)
        now = _now()
        with self._lock:
            self._con.execute("BEGIN IMMEDIATE")
            try:
                self._con.execute(
                    """
                    INSERT INTO runs (
                        id, agent_name, status, prompt, result, error_type, error,
                        state_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        agent_name = excluded.agent_name,
                        status = excluded.status,
                        prompt = COALESCE(excluded.prompt, runs.prompt),
                        result = CASE
                            WHEN excluded.status = 'done' THEN excluded.result
                            ELSE runs.result
                        END,
                        error_type = excluded.error_type,
                        error = excluded.error,
                        state_json = excluded.state_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        run_id, agent_name, status, prompt, result, error_type, error,
                        payload, now, now,
                    ),
                )
                self._con.execute("COMMIT")
            except Exception:
                self._con.execute("ROLLBACK")
                raise

    def set_status(self, run_id: str, status: str) -> None:
        with self._lock:
            self._con.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE id = ?",
                (status, _now(), run_id),
            )

    def list_runs(self, status: str | None = None) -> list[dict]:
        with self._lock:
            if status is None:
                rows = self._con.execute(
                    """
                    SELECT id, agent_name, status, prompt, result, error_type, error,
                           created_at, updated_at
                    FROM runs ORDER BY updated_at DESC
                    """
                ).fetchall()
            else:
                rows = self._con.execute(
                    """
                    SELECT id, agent_name, status, prompt, result, error_type, error,
                           created_at, updated_at
                    FROM runs WHERE status = ? ORDER BY updated_at DESC
                    """,
                    (status,),
                ).fetchall()
        return [dict(r) for r in rows]

    def insert_hitl(
        self,
        request_id: str,
        run_id: str,
        tool_call_id: str,
        agent_name: str | None,
        question: str,
        options: list,
    ) -> None:
        with self._lock:
            self._con.execute("BEGIN IMMEDIATE")
            try:
                self._con.execute(
                    """
                    INSERT INTO hitl (
                        request_id, run_id, tool_call_id, agent_name, question,
                        options_json, response, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
                    ON CONFLICT(run_id, tool_call_id) DO NOTHING
                    """,
                    (
                        request_id, run_id, tool_call_id, agent_name, question,
                        json.dumps(options), _now(),
                    ),
                )
                self._con.execute("COMMIT")
            except Exception:
                self._con.execute("ROLLBACK")
                raise

    def get_hitl(self, run_id: str, tool_call_id: str) -> dict | None:
        with self._lock:
            row = self._con.execute(
                "SELECT * FROM hitl WHERE run_id = ? AND tool_call_id = ?",
                (run_id, tool_call_id),
            ).fetchone()
        return _hitl_row(row)

    def get_hitl_by_request(self, request_id: str) -> dict | None:
        with self._lock:
            row = self._con.execute(
                "SELECT * FROM hitl WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        return _hitl_row(row)

    def save_hitl_response(self, request_id: str, response: str) -> str:
        """Commit an answer. Returns ``saved``, ``missing``, or ``resolved``."""
        with self._lock:
            self._con.execute("BEGIN IMMEDIATE")
            try:
                row = self._con.execute(
                    "SELECT response, run_id FROM hitl WHERE request_id = ?",
                    (request_id,),
                ).fetchone()
                if row is None:
                    self._con.execute("ROLLBACK")
                    return "missing"
                if row["response"] is not None:
                    self._con.execute("ROLLBACK")
                    return "resolved"
                now = _now()
                self._con.execute(
                    "UPDATE hitl SET response = ? WHERE request_id = ?",
                    (response, request_id),
                )
                self._con.execute(
                    """
                    UPDATE runs SET status = 'running', updated_at = ?
                    WHERE id = ? AND status = 'waiting'
                    """,
                    (now, row["run_id"]),
                )
                self._con.execute("COMMIT")
                return "saved"
            except Exception:
                self._con.execute("ROLLBACK")
                raise

    def has_open_hitl(self, run_id: str) -> bool:
        with self._lock:
            row = self._con.execute(
                "SELECT 1 FROM hitl WHERE run_id = ? AND response IS NULL LIMIT 1",
                (run_id,),
            ).fetchone()
        return row is not None

    def pending_hitl(self) -> list[dict]:
        with self._lock:
            rows = self._con.execute(
                "SELECT * FROM hitl WHERE response IS NULL ORDER BY created_at"
            ).fetchall()
        return [r for row in rows if (r := _hitl_row(row)) is not None]


def _hitl_row(row) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    data["options"] = json.loads(data.pop("options_json") or "[]")
    return data


def capture_state(agent) -> dict:
    pad = None
    scratch = agent._scratchpad
    if scratch is not None:
        if scratch._instance is not None:
            pad = {"typed": scratch._instance.model_dump(mode="json")}
        else:
            pad = {"store": dict(scratch._store)}
    return {
        "version": 1,
        "phase": agent._resume_phase,
        "history": agent._history,
        "turn_count": agent._turn_count,
        "running_summary": agent._running_summary,
        "compact_warning_injected": agent._compact_warning_injected,
        "pending_final_content": agent._pending_final_content,
        "no_tools_challenge_count": agent._no_tools_challenge_count,
        "tools_used_this_run": agent._tools_used_this_run,
        "awaiting_final_output": agent._awaiting_final_output,
        "final_output_done": agent._final_output_done,
        "emitted_assistant_content": list(agent._emitted_assistant_content),
        "prompt_tokens": agent._prompt_tokens,
        "last_prompt_tokens": agent._last_prompt_tokens,
        "completion_tokens": agent._completion_tokens,
        "reasoning_tokens": agent._reasoning_tokens,
        "cached_tokens": agent._cached_tokens,
        "api_cost_usd": agent._api_cost_usd,
        "checkpoint_cost_usd": agent._checkpoint_cost_usd,
        "tool_calls_log": agent._tool_calls_log,
        "trace_id": agent._trace_id,
        "span_id": agent._span_id,
        "parent_span_id": agent.parent_span_id,
        "system_prompt": agent.system_prompt,
        "model_id": agent.model,
        "max_turns": agent._max_turns,
        "tool_status": agent._tool_status,
        "result": agent._durable_result,
        "tools_settled": agent._tools_settled,
        "active_tools": sorted(agent._tools),
        "scratchpad": pad,
    }


def restore_runtime(agent, state: dict) -> None:
    """Load everything except the tool registry. Tools are restored after MCP connect."""
    agent._resume_phase = state.get("phase") or "model"
    agent._history = list(state.get("history") or [])
    agent._turn_count = state.get("turn_count") or 0
    agent._running_summary = state.get("running_summary") or ""
    agent._compact_warning_injected = bool(state.get("compact_warning_injected"))
    agent._pending_final_content = state.get("pending_final_content")
    agent._no_tools_challenge_count = state.get("no_tools_challenge_count") or 0
    agent._tools_used_this_run = bool(state.get("tools_used_this_run"))
    agent._awaiting_final_output = bool(state.get("awaiting_final_output"))
    agent._final_output_done = bool(state.get("final_output_done"))
    agent._emitted_assistant_content = list(state.get("emitted_assistant_content") or [])
    agent._prompt_tokens = state.get("prompt_tokens") or 0
    agent._last_prompt_tokens = state.get("last_prompt_tokens") or 0
    agent._completion_tokens = state.get("completion_tokens") or 0
    agent._reasoning_tokens = state.get("reasoning_tokens") or 0
    agent._cached_tokens = state.get("cached_tokens") or 0
    agent._api_cost_usd = state.get("api_cost_usd")
    agent._checkpoint_cost_usd = state.get("checkpoint_cost_usd") or 0.0
    agent._tool_calls_log = list(state.get("tool_calls_log") or [])
    agent._trace_id = state.get("trace_id")
    agent._span_id = state.get("span_id")
    agent.parent_span_id = state.get("parent_span_id")
    agent.system_prompt = state.get("system_prompt", agent.system_prompt)
    agent.model = state.get("model_id", agent.model)
    agent._max_turns = state.get("max_turns", agent._max_turns)
    agent._tool_status = dict(state.get("tool_status") or {})
    agent._durable_result = state.get("result")
    agent._tools_settled = bool(state.get("tools_settled"))
    pad = state.get("scratchpad")
    scratch = agent._scratchpad
    if pad and scratch is None:
        logger.warning(
            "run has scratchpad state but agent %s was built without a scratchpad",
            agent.name,
        )
    elif pad and scratch is not None:
        if "typed" in pad and scratch._schema_class is not None:
            scratch._instance = scratch._schema_class.model_validate(pad["typed"])
        elif "store" in pad:
            scratch._store = dict(pad["store"])


def restore_tools(agent, state: dict) -> None:
    """Match the live registry to the snapshotted active set.

    Called after MCP connect. Deferred tools the run had already expanded are
    moved into the active set. Tools the run had removed are dropped.
    """
    active = set(state.get("active_tools") or [])
    for name in list(getattr(agent, "_deferred_tools", {})):
        if name in active:
            agent._tools[name] = agent._deferred_tools.pop(name)
    groups = getattr(agent, "_deferred_groups", None)
    if groups:
        for group, names in list(groups.items()):
            if any(n not in agent._deferred_tools for n in names):
                groups.pop(group, None)
    for name in list(agent._tools):
        if name not in active:
            agent._tools.pop(name, None)


def tool_calls_from_history(history: list[dict]) -> list[SimpleNamespace]:
    message = None
    for entry in reversed(history):
        if entry.get("role") == "assistant":
            message = entry
            break
    if not message:
        return []
    calls = []
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function") or {}
        calls.append(SimpleNamespace(
            id=tc.get("id"),
            function=SimpleNamespace(
                name=fn.get("name"),
                arguments=fn.get("arguments") or "{}",
            ),
        ))
    return calls
