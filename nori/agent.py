import asyncio
import copy
import json
import logging
import time
import uuid
from typing import Callable

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessage

from nori.anti_spin import Checkpoint, evaluate_checkpoint
import nori.config as config
from nori import tower_sink as _tower_sink
from nori.context import ContextFile, inject_summary, update_running_summary
from nori.enums import ContextRole, OutputFormat, Propagation, SelfModify
from nori.exceptions import AntiSpinTerminated, MaxTurnsExceeded, MCPConnectionError, RunTimeout
from nori.mcp.server import MCPServer
from nori.model import Model
from nori.permissions import Permissions, PermissionGuard
from nori.providers import cost_for, cost_from_ticks
from nori.scratchpad import Scratchpad, _scratchpad_var, _make_owner_tools, _make_propagate_tool
from nori.summarizer import summarize

logger = logging.getLogger("nori.agent")
narration_logger = logging.getLogger("nori.narration")

_UNSET = object()

_COMPACT_WARNING = (
    "[System] Context window is 70% full. Consider wrapping up or calling Compact."
)
_COMPACT_MARKER = "__compact_warning__"

# Exit gate when require_no_tools_ack is on: model must either call tools or
# reply with this sentinel before the loop treats a no-tool turn as final.
_NO_TOOL_CALLS_SENTINEL = "NO_TOOL_CALLS"
_NO_TOOL_CALLS_ACK_MESSAGE = (
    "[System] You produced a response without calling any tools. "
    "If you still need tools, call them now via the function-calling API "
    "(do not write tool calls as prose in your message). "
    f"If you intentionally used no tools, reply with exactly: {_NO_TOOL_CALLS_SENTINEL}"
)

# After tools finish, force one dedicated user-facing reply turn (tool_choice=none).
_FINAL_OUTPUT_MESSAGE = (
    "[System] Tools have finished. Provide the user with a final output now. "
    "Write the complete user-facing reply. Do not call tools."
)

# Optional per-tool status shown while tools run (not the full reply).
_UPDATE_FOR_USER_SCHEMA = {
    "type": "string",
    "description": (
        "Optional one-sentence status update for the user while this tool runs. "
        "Omit if nothing useful to say. Do not put your full reply here — "
        "a separate final-output turn follows after tools finish."
    ),
}


def _is_no_tools_ack(text: str | None) -> bool:
    """True when the model is confirming it intentionally called no tools."""
    if not text:
        return False
    import re

    t = text.strip().upper()
    t = re.sub(r"[‘’`]", "'", t)
    t = re.sub(r"[.!\s]+$", "", t)
    t = re.sub(r"\s+", " ", t)
    return t in {
        "NO_TOOL_CALLS",
        "NO TOOL CALLS",
        "NO-TOOLS",
        "NO TOOLS",
        "I DIDN'T CALL ANY TOOLS",
        "I DID NOT CALL ANY TOOLS",
    }


def _normalize_assistant_prose(text: str) -> str:
    """Collapse whitespace for duplicate detection across agent turns."""
    import re

    return re.sub(r"\s+", " ", text.strip()).lower()


def _is_duplicate_assistant_prose(new: str, prior: str) -> bool:
    """True when *new* is the same user-facing text as *prior* (or a subset).

    Models often re-emit the same caption after a tool returns; chat UIs that
    flush every turn's content would then show it twice.
    """
    n = _normalize_assistant_prose(new)
    p = _normalize_assistant_prose(prior)
    if not n or not p:
        return False
    if n == p:
        return True
    # Minor rephrase that only adds/drops a clause still counts as a dupe if
    # one fully contains the other and both are non-trivial.
    if len(n) >= 12 and len(p) >= 12 and (n in p or p in n):
        return True
    return False


class Agent:
    def __init__(
        self,
        name: str,
        model: Model | None = None,
        system_prompt: str = "",
        tools: list = None,
        mcp_servers: list[MCPServer] = None,
        deferred_tools: list | dict | None = None,
        show_tool_stubs: bool = False,
        max_turns: int | None = _UNSET,
        description: str = "",
        context_files: list[ContextFile] = None,
        permissions: Permissions = None,
        checkpoint: Checkpoint | None = None,
        self_modify: SelfModify | None = None,
        summarize_tool_output: bool = False,
        running_context_summary: bool = False,
        tool_timeout: float | None = _UNSET,
        run_timeout: float | None = _UNSET,
        scratchpad: Scratchpad | None = None,
        output_format: OutputFormat = OutputFormat.TEXT,
        tool_args_filter: Callable[[str, dict], dict] | None = None,
        tool_schema_filter: Callable[[str, dict], dict] | None = None,
        require_no_tools_ack: bool = False,
        no_tools_ack_max: int = 3,
        # Optional override for the no-tools challenge user message.
        no_tools_ack_message: str | None = None,
        # When set, force tool_choice to this function until any tool runs this run.
        # Also rejects NO_TOOL_CALLS while still forcing (cannot opt out).
        force_tool: str | None = None,
    ):
        _d = config.get_defaults()
        model = model or _d.model
        if model is None:
            raise ValueError("Agent requires a model. Pass model= or call nori.configure(model=...).")
        if max_turns is _UNSET:
            max_turns = _d.max_turns if _d.max_turns is not None else 10
        if tool_timeout is _UNSET:
            tool_timeout = _d.tool_timeout
        if run_timeout is _UNSET:
            run_timeout = _d.run_timeout

        if not name:
            raise ValueError("Agent name must be a non-empty string.")
        if max_turns is not None and max_turns <= 0:
            raise ValueError("Agent max_turns must be a positive integer or None.")
        self.name = name
        self._model = model
        self.model: str = model.id
        self.system_prompt = system_prompt
        self.description = description
        self._context_files = context_files or []
        self.__client: AsyncOpenAI | None = None
        self._permissions = PermissionGuard(
            permissions.allow if permissions else None,
            permissions.deny if permissions else None,
        )
        self._max_turns = max_turns
        self._history: list[dict] = []
        self._turn_count = 0
        self.narration: bool = False
        self.narrator_prefix: str = ""
        self.on_narration = self._default_narrator
        # Mid-loop assistant text (content on a tool-call turn). Chat/UI harnesses
        # surface this as user-visible message content; the default falls back to
        # narration so CLI demos still print it.
        self.on_assistant_content = self._default_assistant_content
        self.on_tool_result = self._default_tool_result_handler
        self.summarize_tool_output = summarize_tool_output
        self.running_context_summary = running_context_summary
        self._running_summary: str = ""
        self.max_context_chars: int = model.context_window
        self._compact_warning_injected: bool = False
        self._mcp_servers: list[MCPServer] = list(mcp_servers) if mcp_servers else []
        self._mcp_connections: list = []
        self._self_modify = self_modify
        self._scratchpad: Scratchpad | None = scratchpad
        self.output_format = output_format
        self._checkpoint = checkpoint
        self._register_tools(tools, scratchpad, self_modify, _d)
        self._register_deferred_tools(deferred_tools, show_tool_stubs, _d)
        # Optional hooks: rewrite tool args at invoke time, and/or strip/mutate
        # schemas before they are sent to the model (e.g. force client-side knobs).
        self.tool_args_filter = tool_args_filter
        self.tool_schema_filter = tool_schema_filter
        self.tool_timeout: float | None = tool_timeout
        self.run_timeout: float | None = run_timeout
        # When True and the agent has tools, a no-tool turn cannot end the run
        # until the model either calls tools or replies NO_TOOL_CALLS. Catches
        # "tool call as prose" failures (model narrates a call but never emits one).
        self.require_no_tools_ack = require_no_tools_ack
        if no_tools_ack_max < 1:
            raise ValueError("Agent no_tools_ack_max must be a positive integer.")
        self.no_tools_ack_max = no_tools_ack_max
        # Harness may replace the challenge text (e.g. show-and-tell bias).
        self.no_tools_ack_message = no_tools_ack_message or _NO_TOOL_CALLS_ACK_MESSAGE
        # Optional: pin tool_choice to this function name until a real tool runs.
        self.force_tool = force_tool
        self._pending_final_content: str | None = None
        self._no_tools_challenge_count = 0
        # True once any real tool ran this run — skip the NO_TOOL_CALLS gate after that.
        self._tools_used_this_run = False
        # After tools stop: inject FINAL_OUTPUT_MESSAGE, then one tool_choice=none turn.
        self._awaiting_final_output = False
        self._final_output_done = False
        # Prose already flushed via on_assistant_content this run (dedupe repeats).
        self._emitted_assistant_content: list[str] = []
        self._run_start: float | None = None
        self._elapsed: float | None = None
        self._prompt_tokens: int = 0
        self._last_prompt_tokens: int = 0
        self._completion_tokens: int = 0
        # Chain-of-thought tokens (xAI reasoning models). Billed as output, not
        # included in completion_tokens. See completion_tokens_details.reasoning_tokens.
        self._reasoning_tokens: int = 0
        # Prompt tokens served from provider cache (subset of prompt_tokens).
        self._cached_tokens: int = 0
        # Sum of provider-reported cost_in_usd_ticks converted to USD, when present.
        self._api_cost_usd: float | None = None
        # Optional sticky conversation id for prompt-cache routing (x-grok-conv-id).
        # Chat harnesses may stamp this from the client request.
        self.conversation_id: str | None = None
        # Optional per-run tail (datetime, knobs). Appended after the user prompt so
        # the system message stays a stable cacheable prefix. Not part of UI history.
        self.dynamic_context: str | None = None
        self._tool_calls_log: list[dict] = []
        self.auditor = None
        self.narration_call_id: bool = True
        self.narration_trace_id: bool = False
        self.narration_summary: bool = True
        self._trace_id: str | None = None
        self._span_id: str | None = None
        self.parent_span_id: str | None = None

    @property
    def trace_id(self) -> str | None:
        return self._trace_id

    @property
    def span_id(self) -> str | None:
        return self._span_id

    @property
    def _client(self) -> AsyncOpenAI:
        if self.__client is None:
            if self._model.http_client is not None:
                self.__client = AsyncOpenAI(
                    http_client=self._model.http_client,
                    base_url=self._model.base_url,
                    api_key="nori",  # SDK requires non-empty; ignored when http_client is set
                )
            else:
                self.__client = AsyncOpenAI(
                    api_key=self._model.api_key,
                    base_url=self._model.base_url,
                )
        return self.__client

    # ── Self-modification ─────────────────────────────────────────────────────

    def _register_self_modify_tools(self, level: SelfModify) -> None:
        from nori.tools.self_modify.custodian import make_custodian_tools
        from nori.tools.self_modify.modify import make_modify_tools
        from nori.tools.self_modify.mutation import make_mutation_tools

        for t in make_custodian_tools(self):
            self._tools[self._tool_name(t)] = t
        if level in (SelfModify.MODIFY, SelfModify.MUTATION):
            for t in make_modify_tools(self):
                self._tools[self._tool_name(t)] = t
        if level is SelfModify.MUTATION:
            for t in make_mutation_tools(self):
                self._tools[self._tool_name(t)] = t

    def _register_tools(self, tools: list, scratchpad, self_modify, defaults) -> None:
        self._tools: dict = {self._tool_name(t): t for t in (tools or [])}
        for t in self._tools.values():
            if hasattr(t, "model") and t.model is None:
                t.model = defaults.tool_models.get(t) or defaults.tool_models.get(type(t)) or self._model
        if self_modify is not None:
            self._register_self_modify_tools(self_modify)
        if scratchpad is not None:
            read_tool, write_tool = _make_owner_tools(scratchpad)
            self._tools[self._tool_name(read_tool)] = read_tool
            self._tools[self._tool_name(write_tool)] = write_tool
            if scratchpad.propagate == Propagation.DISCRETIONARY:
                propagate_tool = _make_propagate_tool(scratchpad)
                self._tools[self._tool_name(propagate_tool)] = propagate_tool

    def _register_deferred_tools(self, deferred_tools, show_tool_stubs: bool, defaults) -> None:
        self._show_tool_stubs = show_tool_stubs
        self._deferred_tools: dict[str, object] = {}
        self._deferred_groups: dict[str, list[str]] = {}

        if not deferred_tools:
            return

        items = deferred_tools.items() if isinstance(deferred_tools, dict) else [(None, deferred_tools)]
        for group_name, tool_list in items:
            names = []
            for t in tool_list:
                name = self._tool_name(t)
                self._deferred_tools[name] = t
                if hasattr(t, "model") and t.model is None:
                    t.model = defaults.tool_models.get(t) or defaults.tool_models.get(type(t)) or self._model
                names.append(name)
            if group_name is not None:
                self._deferred_groups[group_name] = names

    def _expand_tool_schema(self) -> dict:
        tool_list = list(self._deferred_tools.keys())
        group_list = [f"{g} (group: {', '.join(ns)})" for g, ns in self._deferred_groups.items()]
        available = ", ".join(tool_list + group_list) or "none"
        return {
            "type": "function",
            "function": {
                "name": "ExpandTool",
                "description": f"Load a deferred tool or tool group into your active tool set so you can call it. Available: {available}",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tool_name": {"type": "string", "description": "Name of the tool or group to expand."},
                        "reason": {"type": "string", "description": "Your reason for expanding this tool."},
                    },
                    "required": ["tool_name", "reason"],
                },
            },
        }

    def _deferred_tools_prompt(self) -> str:
        lines = ["## Deferred Tools",
                 "These tools are available but not yet loaded. Call ExpandTool(tool_name) to load one, then call it directly."]
        for name, t in self._deferred_tools.items():
            desc = t.schema["function"]["description"].split("\n")[0]
            lines.append(f"- {name}: {desc}")
        if self._deferred_groups:
            lines.append("")
            lines.append("Groups (expand all tools in a group at once):")
            for group, names in self._deferred_groups.items():
                lines.append(f"- {group}: {', '.join(names)}")
        return "\n".join(lines)

    async def _handle_expand_tool_call(self, tc) -> dict:
        args = json.loads(tc.function.arguments)
        name = args.get("tool_name", "").strip()

        if name in self._deferred_groups:
            expanded = []
            for tn in self._deferred_groups.pop(name):
                if tn in self._deferred_tools:
                    self._tools[tn] = self._deferred_tools.pop(tn)
                    expanded.append(tn)
            msg = f"Group '{name}' expanded: {', '.join(expanded)} are now available. Call them directly."
            return {"role": "tool", "tool_call_id": tc.id, "content": msg}

        if name not in self._deferred_tools:
            available = list(self._deferred_tools.keys()) + list(self._deferred_groups.keys())
            return {"role": "tool", "tool_call_id": tc.id,
                    "content": f"Unknown tool '{name}'. Available: {', '.join(available) or 'none'}"}

        self._tools[name] = self._deferred_tools.pop(name)
        return {"role": "tool", "tool_call_id": tc.id,
                "content": f"{name} is now available. Call it directly."}

    # ── MCP ───────────────────────────────────────────────────────────────────

    @property
    def mcp_servers(self) -> list[MCPServer]:
        return self._mcp_servers

    def add_mcp_server(self, server: MCPServer) -> None:
        self._mcp_servers.append(server)

    def remove_mcp_server(self, name: str) -> None:
        self._mcp_servers = [s for s in self._mcp_servers if s.name != name]

    async def _connect_mcp(self) -> None:
        """Connect to all configured MCP servers and register their tools."""
        if not self._mcp_servers:
            return
        from nori.mcp.client import MCPConnection

        for server in self._mcp_servers:
            conn = MCPConnection(server)
            try:
                tools = await conn.connect()
            except Exception as exc:
                await conn.aclose()
                if server.command:
                    hint = (
                        f"Check that '{server.command}' is installed and on PATH, "
                        f"and that any environment variables it needs (e.g. API keys) are set."
                    )
                else:
                    hint = f"Check that the url '{server.url}' is correct and reachable."
                raise MCPConnectionError(
                    f"Failed to connect to MCP server '{server.name}': {exc}\n{hint}"
                ) from exc
            self._mcp_connections.append(conn)
            for t in tools:
                name = t.schema["function"]["name"]
                if name in self._tools:
                    logger.warning(
                        "mcp tool '%s' from server '%s' overrides an existing tool",
                        name, server.name,
                    )
                self._tools[name] = t
            logger.debug("mcp_connected server=%s tools=%d", server.name, len(tools))

    async def _disconnect_mcp(self) -> None:
        """Tear down MCP connections and unregister their tools."""
        for conn in self._mcp_connections:
            for t in conn.tools:
                self._tools.pop(t.schema["function"]["name"], None)
            try:
                await conn.aclose()
            except Exception as exc:
                logger.warning("mcp_disconnect_error server=%s error=%s", conn.server.name, exc)
        self._mcp_connections = []

    @staticmethod
    def _inject_reason_into_schema(schema: dict) -> dict:
        """Ensure a discovered MCP tool schema has 'reason' and 'summary' in its required params."""
        import copy
        schema = copy.deepcopy(schema)
        params = schema.get("function", {}).get("parameters", {})
        props = params.setdefault("properties", {})
        required = params.setdefault("required", [])
        if "reason" not in props:
            props["reason"] = {"type": "string", "description": "Your reason for calling this tool."}
        if "reason" not in required:
            required.append("reason")
        if "summary" not in props:
            props["summary"] = {"type": "string", "description": "One-line narration summary of what this tool call found or did. Be specific: include key values, filenames, counts, or outcomes — not just 'read file' or 'ran command'."}
        if "summary" not in required:
            required.append("summary")
        if "update_for_user" not in props:
            props["update_for_user"] = dict(_UPDATE_FOR_USER_SCHEMA)
        return schema

    @staticmethod
    def _inject_update_for_user_into_schema(schema: dict) -> dict:
        """Ensure every tool schema exposes optional update_for_user (not required)."""
        params = schema.get("function", {}).get("parameters", {})
        if not isinstance(params, dict):
            return schema
        props = params.setdefault("properties", {})
        if "update_for_user" not in props:
            props["update_for_user"] = dict(_UPDATE_FOR_USER_SCHEMA)
        return schema

    # ── Tool interface (Agent as a tool) ─────────────────────────────────────

    @property
    def schema(self) -> dict:
        desc = self.description or self.system_prompt or f"Run the {self.name} agent."
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string"},
                        "reason": {"type": "string", "description": "Your reason for calling this agent."},
                    },
                    "required": ["task", "reason"],
                },
            },
        }

    @property
    def summarize_output(self) -> bool:
        return True

    def _clone(self) -> "Agent":
        """Fresh Agent with this agent's configuration and none of its run state."""
        _perms = None
        if self._permissions._allow or self._permissions._deny:
            _perms = Permissions(
                allow=self._permissions._allow,
                deny=self._permissions._deny,
            )
        deferred = list(self._deferred_tools.values()) if self._deferred_tools else None
        return Agent(
            name=self.name,
            model=self._model,
            system_prompt=self.system_prompt,
            tools=list(self._tools.values()),
            mcp_servers=list(self._mcp_servers),
            deferred_tools=deferred,
            show_tool_stubs=self._show_tool_stubs,
            max_turns=self._max_turns,
            description=self.description,
            context_files=self._context_files,
            permissions=_perms,
            checkpoint=self._checkpoint,
            self_modify=self._self_modify,
            summarize_tool_output=self.summarize_tool_output,
            running_context_summary=self.running_context_summary,
            tool_timeout=self.tool_timeout,
            run_timeout=self.run_timeout,
            scratchpad=self._scratchpad,
            output_format=self.output_format,
            tool_args_filter=self.tool_args_filter,
            tool_schema_filter=self.tool_schema_filter,
            require_no_tools_ack=self.require_no_tools_ack,
            no_tools_ack_max=self.no_tools_ack_max,
            no_tools_ack_message=self.no_tools_ack_message,
            force_tool=self.force_tool,
        )

    async def __call__(self, task: str, reason: str = "") -> str:
        sub = self._clone()
        return await sub.run(task, _trace_id=self._trace_id, _parent_span_id=self._span_id)

    def _audit(self, method: str, **kwargs) -> None:
        if self.auditor:
            getattr(self.auditor, method)(**kwargs)
        _tower_sink.emit(method, **kwargs)

    def _context_fill(self) -> float:
        # Current fill is the last completion's prompt size, not the cumulative
        # count — each turn resends the whole history, so the running total
        # overstates fill more every turn.
        if not self.max_context_chars:
            return 0.0
        return self._last_prompt_tokens / self.max_context_chars

    async def _compact(self, fill: float = 0.0) -> None:
        self._running_summary = await update_running_summary(
            self._history, self._running_summary, self._client, self.model
        )
        self._history = inject_summary(self._history, self._running_summary)
        self._compact_warning_injected = False
        msg = f"{self.narrator_prefix}{self.name}[Context compacted ({fill:.0%} full)]"
        narration_logger.debug(msg)
        if self.narration:
            self.on_narration(msg)
        self._audit(
            "compaction",
            agent=self.name, fill=fill,
            trace_id=self._trace_id, span_id=self._span_id,
            parent_span_id=self.parent_span_id,
        )

    async def _handle_context_pressure(self, fill: float) -> None:
        if fill >= 0.85:
            await self._compact(fill=fill)
        elif fill >= 0.70 and not self._compact_warning_injected:
            self._history.append({
                "role": "user",
                "content": _COMPACT_WARNING,
                "_marker": _COMPACT_MARKER,
            })
            self._compact_warning_injected = True
            warn_msg = f"{self.narrator_prefix}{self.name}[Context warning ({fill:.0%} full)]"
            narration_logger.debug(warn_msg)
            if self.narration:
                self.on_narration(warn_msg)

    async def _run_checkpoint(self) -> None:
        recent = self._history[-self._checkpoint.every * 4:]
        is_spin, summary = await evaluate_checkpoint(
            recent, self._checkpoint.scrutiny, self._client, self.model
        )
        if is_spin:
            raise AntiSpinTerminated(
                f"Anti-spin triggered at turn {self._turn_count}. Summary: {summary}"
            )
        if self._checkpoint.compact:
            self._history = inject_summary(self._history, summary)

    async def _handle_compact_call(self, tc) -> dict:
        await self._compact(fill=self._context_fill())
        return {"role": "tool", "tool_call_id": tc.id, "content": "History compacted."}

    def _default_narrator(self, text: str) -> None:
        print(text)

    def _default_assistant_content(self, text: str) -> None:
        """Default: route mid-loop prose through narration (CLI-friendly)."""
        if not text or not self.narration:
            return
        msg = f"{self.narrator_prefix}{text}"
        narration_logger.debug(msg)
        self.on_narration(msg)

    def _emit_assistant_content(self, text: str | None) -> bool:
        """Flush user-visible assistant prose once per distinct block this run.

        Returns True if the callback was invoked. Skips empty text and blocks that
        duplicate something already streamed (common after tool turns).
        """
        if not text or not text.strip():
            return False
        for prior in self._emitted_assistant_content:
            if _is_duplicate_assistant_prose(text, prior):
                logger.debug(
                    "assistant_content_deduped agent=%s chars=%d",
                    self.name, len(text),
                )
                return False
        self._emitted_assistant_content.append(text)
        self.on_assistant_content(text)
        return True

    def _default_tool_result_handler(self, name: str, result: str, call_id: str | None, trace_id: str | None) -> None:
        pass

    def _narrate(self, tool_name: str, reason: str, call_id: str | None = None, is_parallel: bool = False) -> None:
        if is_parallel and self.narration_call_id and call_id:
            name_part = f"{tool_name}-{call_id}"
            suffix = f"[Started: {reason}]"
        else:
            name_part = tool_name
            suffix = f"[{reason}]"

        if self.narration_trace_id and self._trace_id:
            msg = f"{self.narrator_prefix}{self.name} → {name_part}[{self._trace_id}]{suffix}"
        else:
            msg = f"{self.narrator_prefix}{self.name} → {name_part}{suffix}"

        narration_logger.debug(msg)
        if self.narration:
            self.on_narration(msg)

    def _narrate_summary(self) -> None:
        if not self.narration or not self.narration_summary:
            return
        total = self._prompt_tokens + self._completion_tokens + self._reasoning_tokens
        elapsed_part = f" | {self._elapsed:.1f}s" if self._elapsed is not None else ""
        msg = (
            f"{self.narrator_prefix}{self.name}: "
            f"{self._turn_count} turns | {total:,} tokens | ${self.cost:.4f}{elapsed_part}"
        )
        narration_logger.debug(msg)
        self.on_narration(msg)

    def _narrate_elapsed(self, tool_name: str, elapsed: float, call_id: str | None, is_parallel: bool) -> None:
        if not self.narration:
            return
        if is_parallel and self.narration_call_id and call_id:
            name_part = f"{tool_name}-{call_id}"
        else:
            name_part = tool_name
        msg = f"{self.narrator_prefix}{self.name} → {name_part}[{elapsed:.2f}s]"
        narration_logger.debug(msg)
        self.on_narration(msg)

    def _narrate_result(self, tool_name: str, result: str, call_id: str | None, is_parallel: bool) -> None:
        if not self.narration or not is_parallel or not self.narration_call_id or not call_id:
            return
        flat = result.replace("\n", " | ")
        name_part = f"{tool_name}-{call_id}"
        if self.narration_trace_id and self._trace_id:
            msg = f"{self.narrator_prefix}{self.name} → {name_part}[{self._trace_id}][Result: {flat}]"
        else:
            msg = f"{self.narrator_prefix}{self.name} → {name_part}[Result: {flat}]"
        narration_logger.debug(msg)
        self.on_narration(msg)

    def _tool_name(self, t) -> str:
        return t.schema["function"]["name"]

    def _tool_schemas(self) -> list[dict]:
        schemas = []
        for t in self._tools.values():
            schema = copy.deepcopy(t.schema)
            if self.tool_schema_filter is not None:
                name = self._tool_name(t)
                schema = self.tool_schema_filter(name, schema)
            schema = self._inject_update_for_user_into_schema(schema)
            schemas.append(schema)
        if self._show_tool_stubs and self._deferred_tools:
            schemas.append(self._expand_tool_schema())
        return schemas

    def _apply_strips(self) -> None:
        """After a completion, remove ephemeral image content from history."""
        for i, m in enumerate(self._history):
            if m.get("_strip_after_read"):
                self._history[i] = {k: v for k, v in m.items() if k != "_strip_after_read"}
                self._history[i]["content"] = "[image result stripped]"
            if isinstance(m.get("content"), list):
                new_parts = []
                changed = False
                for part in m["content"]:
                    if part.get("_strip"):
                        new_parts.append({"type": "text", "text": "[image stripped]"})
                        changed = True
                    else:
                        new_parts.append(part)
                if changed:
                    self._history[i] = {**m, "content": new_parts}

    def _build_messages(self, history: list[dict]) -> list[dict]:
        system_content = self.system_prompt

        pad = self._scratchpad or _scratchpad_var.get()
        if pad is not None:
            parts = []
            usage = pad.usage_prompt()
            if usage:
                parts.append(usage)
            parts.append(pad.schema_prompt())
            system_content += "\n\n" + "\n\n".join(parts)

        for cf in self._context_files:
            if cf.role == ContextRole.SYSTEM:
                system_content += "\n\n" + cf.content

        if self._show_tool_stubs and self._deferred_tools:
            system_content += "\n\n" + self._deferred_tools_prompt()

        messages = [{"role": "system", "content": system_content}]

        for cf in self._context_files:
            if cf.role == ContextRole.USER:
                messages.append({"role": "user", "content": cf.content})
            elif cf.role == ContextRole.ASSISTANT:
                messages.append({"role": "assistant", "content": cf.content})

        messages.extend(self._clean_history(history))
        return messages

    @staticmethod
    def _clean_history(history: list[dict]) -> list[dict]:
        """Strip internal metadata keys before sending to the API."""
        cleaned = []
        for m in history:
            if "_strip_after_read" in m or (
                isinstance(m.get("content"), list) and
                any("_strip" in part for part in m["content"])
            ):
                m = dict(m)
                m.pop("_strip_after_read", None)
                if isinstance(m.get("content"), list):
                    m["content"] = [{k: v for k, v in part.items() if k != "_strip"} for part in m["content"]]
            cleaned.append(m)
        return cleaned

    def _message_to_dict(self, message: ChatCompletionMessage) -> dict:
        d: dict = {"role": "assistant", "content": message.content}
        if message.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]
        # xAI reasoning models: echo reasoning_content on later turns or multi-turn
        # prompt cache misses (top miss cause per xAI docs).
        reasoning = getattr(message, "reasoning_content", None)
        if reasoning is None:
            extra = getattr(message, "model_extra", None)
            if isinstance(extra, dict):
                reasoning = extra.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning:
            d["reasoning_content"] = reasoning
        return d

    async def _invoke_tool(self, tc, is_parallel: bool = False) -> dict:
        if tc.function.name == "Compact":
            return await self._handle_compact_call(tc)
        if tc.function.name == "ExpandTool":
            return await self._handle_expand_tool_call(tc)
        self._permissions.check(tc.function.name)
        fn = self._tools[tc.function.name]
        args = json.loads(tc.function.arguments)
        if self.tool_args_filter is not None:
            args = self.tool_args_filter(tc.function.name, args)
        # User-facing status while tools run — not free-form assistant content.
        update = args.pop("update_for_user", None)
        if isinstance(update, str) and update.strip():
            self._emit_assistant_content(update.strip())
        reason = args.get("reason", "")
        tool_span_id = uuid.uuid4().hex[:8]
        tool_call_id = tool_span_id[:4]
        self._narrate(tc.function.name, reason, tool_call_id, is_parallel)
        logger.debug("tool_call name=%s args=%s", tc.function.name, args)
        self._audit(
            "tool_call",
            agent=self.name, name=tc.function.name, args=args,
            trace_id=self._trace_id, span_id=tool_span_id,
            parent_span_id=self._span_id, call_id=tool_call_id,
        )
        tool_start = time.perf_counter()
        try:
            if self.tool_timeout is not None:
                result = await asyncio.wait_for(fn(**args), timeout=self.tool_timeout)
            else:
                result = await fn(**args)
        except asyncio.TimeoutError:
            msg = f"[ToolTimeout: {tc.function.name} did not complete within {self.tool_timeout}s]"
            logger.warning("tool_timeout name=%s timeout=%s", tc.function.name, self.tool_timeout)
            narrate_msg = f"{self.narrator_prefix}{self.name} → {tc.function.name}[Timed out after {self.tool_timeout}s]"
            narration_logger.debug(narrate_msg)
            if self.narration:
                self.on_narration(narrate_msg)
            self._audit(
                "tool_error",
                agent=self.name, name=tc.function.name, error=msg,
                trace_id=self._trace_id, span_id=tool_span_id,
                parent_span_id=self._span_id, call_id=tool_call_id,
            )
            return {"role": "tool", "tool_call_id": tc.id, "content": msg}
        except Exception as exc:
            logger.error("tool_error name=%s error=%s", tc.function.name, exc)
            self._audit(
                "tool_error",
                agent=self.name, name=tc.function.name, error=str(exc),
                trace_id=self._trace_id, span_id=tool_span_id,
                parent_span_id=self._span_id, call_id=tool_call_id,
            )
            raise
        tool_elapsed = time.perf_counter() - tool_start
        content = result.result if hasattr(result, "result") else str(result)
        content = content or "[EMPTY]"
        if self.summarize_tool_output and getattr(fn, "summarize_output", True):
            content = await summarize(content, reason, self._client, self.model)
        logger.debug("tool_result name=%s result=%s elapsed=%.2fs", tc.function.name, content, tool_elapsed)
        self._narrate_elapsed(tc.function.name, tool_elapsed, tool_call_id, is_parallel)
        self._narrate_result(tc.function.name, content, tool_call_id, is_parallel)
        self._audit(
            "tool_result",
            agent=self.name, name=tc.function.name, result=content,
            trace_id=self._trace_id, span_id=tool_span_id,
            parent_span_id=self._span_id, call_id=tool_call_id,
        )
        self._tool_calls_log.append({"name": tc.function.name, "args": args, "result": content})
        self.on_tool_result(tc.function.name, content, tool_call_id, self._trace_id)
        tool_msg: dict = {"role": "tool", "tool_call_id": tc.id, "content": content}
        if args.get("remove_from_context_after_read"):
            tool_msg["_strip_after_read"] = True
        return tool_msg

    async def _execute_tools(self, tool_calls) -> list[dict]:
        is_parallel = len(tool_calls) > 1
        return list(await asyncio.gather(*[self._invoke_tool(tc, is_parallel) for tc in tool_calls]))

    def _force_tool_active(self) -> bool:
        """True when force_tool is set and no real tool has run yet this run."""
        return bool(self.force_tool) and not self._tools_used_this_run

    async def _complete(self, history: list[dict]) -> ChatCompletionMessage:
        messages = self._build_messages(history)
        kwargs: dict = {**self._model.completion_kwargs(), "messages": messages}
        if self._tools:
            kwargs["tools"] = self._tool_schemas()
            # Final-output turn: text only — no more tools.
            if self._awaiting_final_output:
                kwargs["tool_choice"] = "none"
            # Pin tool_choice while force_tool is active (e.g. user asked for a pic).
            elif self._force_tool_active():
                names = {
                    s.get("function", {}).get("name")
                    for s in kwargs["tools"]
                    if isinstance(s, dict)
                }
                if self.force_tool in names:
                    kwargs["tool_choice"] = {
                        "type": "function",
                        "function": {"name": self.force_tool},
                    }
        # Sticky routing for xAI prompt cache (and harmless elsewhere).
        conv_id = getattr(self, "conversation_id", None)
        if isinstance(conv_id, str) and conv_id.strip():
            kwargs["extra_headers"] = {"x-grok-conv-id": conv_id.strip()}
        response = await self._client.chat.completions.create(**kwargs)
        if response.usage:
            self._record_usage(response.usage)
        return response.choices[0].message

    def _record_usage(self, usage) -> None:
        """Accumulate provider usage. Includes reasoning tokens and exact $ ticks when present."""
        pt = getattr(usage, "prompt_tokens", None)
        ct = getattr(usage, "completion_tokens", None)
        if isinstance(pt, int):
            self._prompt_tokens += pt
            self._last_prompt_tokens = pt
        else:
            pt = 0
        if isinstance(ct, int):
            self._completion_tokens += ct
        else:
            ct = 0

        rt = 0
        details = getattr(usage, "completion_tokens_details", None)
        if details is not None:
            raw = (
                details.get("reasoning_tokens")
                if isinstance(details, dict)
                else getattr(details, "reasoning_tokens", None)
            )
            if isinstance(raw, int):
                rt = raw

        # total_tokens often includes reasoning even when details are missing.
        total = getattr(usage, "total_tokens", None)
        if isinstance(total, int) and total >= (pt or 0) + (ct or 0):
            unaccounted = total - (pt or 0) - (ct or 0)
            if unaccounted > rt:
                rt = unaccounted

        if rt:
            self._reasoning_tokens += rt

        # Cached prompt tokens (xAI / OpenAI-style prompt_tokens_details).
        cached = 0
        pdetails = getattr(usage, "prompt_tokens_details", None)
        if pdetails is not None:
            raw_c = (
                pdetails.get("cached_tokens")
                if isinstance(pdetails, dict)
                else getattr(pdetails, "cached_tokens", None)
            )
            if isinstance(raw_c, int) and raw_c > 0:
                cached = raw_c
        if cached:
            self._cached_tokens += cached

        ticks = getattr(usage, "cost_in_usd_ticks", None)
        if isinstance(ticks, int) and ticks >= 0:
            piece = cost_from_ticks(ticks)
            self._api_cost_usd = (self._api_cost_usd or 0.0) + piece

    # ── QoL properties ────────────────────────────────────────────────────────

    @property
    def history(self) -> list[dict]:
        return self._history

    @property
    def turn_count(self) -> int:
        return self._turn_count

    @property
    def token_counts(self) -> dict[str, int]:
        return {
            "prompt": self._prompt_tokens,
            "completion": self._completion_tokens,
            "reasoning": self._reasoning_tokens,
            "cached": self._cached_tokens,
            "total": self._prompt_tokens + self._completion_tokens + self._reasoning_tokens,
        }

    @property
    def cost(self) -> float:
        # Prefer provider-reported billed cost (includes cache discounts, reasoning, tools).
        if self._api_cost_usd is not None:
            return self._api_cost_usd
        return cost_for(
            self.model,
            self._prompt_tokens,
            self._completion_tokens,
            reasoning_tokens=self._reasoning_tokens,
        )

    @property
    def context_length(self) -> int:
        return self._prompt_tokens + self._completion_tokens + self._reasoning_tokens

    @property
    def tool_calls(self) -> list[dict]:
        return self._tool_calls_log

    @property
    def elapsed(self) -> float | None:
        """Seconds elapsed during the last run(). None if run() hasn't been called."""
        return self._elapsed

    def reset(self) -> None:
        self._history = []
        self._turn_count = 0
        self._prompt_tokens = 0
        self._last_prompt_tokens = 0
        self._completion_tokens = 0
        self._reasoning_tokens = 0
        self._cached_tokens = 0
        self._api_cost_usd = None
        self._tool_calls_log = []
        self._running_summary = ""
        self._compact_warning_injected = False
        self._pending_final_content = None
        self._no_tools_challenge_count = 0
        self._tools_used_this_run = False
        self._awaiting_final_output = False
        self._final_output_done = False
        self._emitted_assistant_content = []
        self._trace_id = None
        self._span_id = None
        self.parent_span_id = None
        self._run_start = None
        self._elapsed = None

    async def _finish_without_tools_async(self, result: str) -> str:
        """Shared exit path when the run ends on a no-tool turn."""
        if self.running_context_summary:
            self._running_summary = await update_running_summary(
                self._history, self._running_summary, self._client, self.model
            )
            self._history = inject_summary(self._history, self._running_summary)
        self._narrate_summary()
        self._audit(
            "agent_end",
            agent=self.name, result=result, turns=self._turn_count, cost=self.cost,
            prompt_tokens=self._prompt_tokens, completion_tokens=self._completion_tokens,
            trace_id=self._trace_id, span_id=self._span_id,
            parent_span_id=self.parent_span_id,
        )
        return result

    async def run(
        self,
        prompt: str,
        images: list = None,
        _trace_id: str | None = None,
        _parent_span_id: str | None = None,
    ) -> str | dict:
        self._trace_id = _trace_id or str(uuid.uuid4())
        self._span_id = uuid.uuid4().hex[:8]
        if _parent_span_id:
            self.parent_span_id = _parent_span_id
        logger.debug("run agent=%s prompt=%r", self.name, prompt[:80])
        self._audit(
            "agent_start",
            agent=self.name, prompt=prompt,
            trace_id=self._trace_id, span_id=self._span_id,
            parent_span_id=self.parent_span_id,
        )
        if self.narration:
            preview = prompt[:120].replace("\n", " ")
            if len(prompt) > 120:
                preview += "..."
            start_msg = f"{self.narrator_prefix}{self.name}[{preview}]"
            narration_logger.debug(start_msg)
            self.on_narration(start_msg)
        if images:
            content: list = [{"type": "text", "text": prompt}]
            content += [img.to_content_part() for img in images]
            self._history.append({"role": "user", "content": content})
        else:
            self._history.append({"role": "user", "content": prompt})

        # Per-turn dynamic tail (clock, product knobs) after the user message so
        # the system prompt remains a stable prefix for provider prompt caching.
        dyn = getattr(self, "dynamic_context", None)
        if isinstance(dyn, str) and dyn.strip():
            self._history.append({"role": "user", "content": dyn.strip()})

        _d = config.get_defaults()
        _ctx_server = None
        _ctx_token = None
        if _d.server.enabled:
            from nori import server as _ctx_server
            await _ctx_server.ensure_started(_d.server)
            _ctx_token = _ctx_server._agent_name_var.set(self.name)

        _ctx_pad_token = None
        if self._scratchpad is not None and self._scratchpad.propagate == Propagation.ALWAYS:
            _ctx_pad_token = _scratchpad_var.set(self._scratchpad)

        self._run_start = time.perf_counter()
        try:
            await self._connect_mcp()
            async with asyncio.timeout(self.run_timeout):
                result = await self._run_loop()
            self._elapsed = time.perf_counter() - self._run_start
            if self.output_format == OutputFormat.OPENAI_CHAT:
                return {"role": "assistant", "content": result}
            if self.output_format == OutputFormat.OPENAI_RESPONSES:
                return {"role": "assistant", "content": [{"type": "output_text", "text": result}]}
            return result
        except asyncio.TimeoutError:
            self._elapsed = time.perf_counter() - self._run_start
            raise RunTimeout(
                f"{self.name} exceeded run_timeout={self.run_timeout}s "
                f"after {self._turn_count} turns"
            )
        finally:
            await self._disconnect_mcp()
            if _ctx_token is not None:
                _ctx_server._agent_name_var.reset(_ctx_token)
            if _ctx_pad_token is not None:
                _scratchpad_var.reset(_ctx_pad_token)
            if self._scratchpad is not None:
                self._scratchpad.dump_audit(self.name)

    async def _run_loop(self) -> str:
        self._pending_final_content = None
        self._no_tools_challenge_count = 0
        self._tools_used_this_run = False
        self._awaiting_final_output = False
        self._final_output_done = False
        self._emitted_assistant_content = []
        while True:
            # Allow one extra completion for the forced final-output pass after tools.
            at_limit = self._max_turns is not None and self._turn_count >= self._max_turns
            if (
                at_limit
                and self._tools_used_this_run
                and not self._final_output_done
                and not self._awaiting_final_output
            ):
                # Hit the ceiling mid-run after tools: still take the final-output turn.
                logger.debug("final_output_pass_at_max_turns agent=%s", self.name)
                self._awaiting_final_output = True
                self._history.append({"role": "user", "content": _FINAL_OUTPUT_MESSAGE})
            if at_limit and not self._awaiting_final_output:
                raise MaxTurnsExceeded(f"Reached max_turns={self._max_turns}")

            message = await self._complete(self._history)
            self._apply_strips()
            self._turn_count += 1
            logger.debug("turn agent=%s turn=%d tool_calls=%d",
                         self.name, self._turn_count,
                         len(message.tool_calls) if message.tool_calls else 0)
            self._history.append(self._message_to_dict(message))

            await self._handle_context_pressure(self._context_fill())

            if self._checkpoint and self._turn_count % self._checkpoint.every == 0:
                await self._run_checkpoint()

            # Forced final-output turn (tool_choice=none) after tools finished.
            if self._awaiting_final_output:
                self._awaiting_final_output = False
                self._final_output_done = True
                if _is_no_tools_ack(message.content):
                    result = self._pending_final_content or ""
                    return await self._finish_without_tools_async(result)
                if message.content:
                    self._emit_assistant_content(message.content)
                    self._pending_final_content = message.content
                result = self._pending_final_content or (message.content or "")
                return await self._finish_without_tools_async(result)

            if message.tool_calls:
                # Free-form message.content on tool turns is not user-facing.
                # Status goes through optional tool arg update_for_user (emitted
                # as each tool starts). Full reply comes on the final-output pass.
                # Real tool use clears the no-tools exit gate for the rest of this run.
                self._no_tools_challenge_count = 0
                self._tools_used_this_run = True
                self._final_output_done = False
                tool_results = await self._execute_tools(message.tool_calls)
                self._history.extend(tool_results)
                continue

            # ── No tool calls this turn ──────────────────────────────────────
            # After real tools ran, force one dedicated final-output turn rather
            # than treating this (often empty or re-caption) reply as the answer.
            if self._tools_used_this_run and not self._final_output_done:
                logger.debug("final_output_pass agent=%s", self.name)
                self._awaiting_final_output = True
                self._history.append({"role": "user", "content": _FINAL_OUTPUT_MESSAGE})
                continue

            # Optional gate: when tools exist and require_no_tools_ack is on, the
            # model must either call tools or explicitly say NO_TOOL_CALLS before
            # we end the run. Stops "tool call as prose" from counting as done.
            if self.require_no_tools_ack and self._tools and not self._tools_used_this_run:
                if _is_no_tools_ack(message.content):
                    # force_tool active → cannot opt out with NO_TOOL_CALLS.
                    if self._force_tool_active():
                        self._no_tools_challenge_count += 1
                        if self._no_tools_challenge_count >= self.no_tools_ack_max:
                            logger.warning(
                                "force_tool_ack_exhausted agent=%s tool=%s attempts=%d",
                                self.name, self.force_tool, self._no_tools_challenge_count,
                            )
                            result = self._pending_final_content or ""
                            return await self._finish_without_tools_async(result)
                        self._history.append({
                            "role": "user",
                            "content": (
                                f"[System] You must call {self.force_tool} via the "
                                "function-calling API now. Do not reply with "
                                f"{_NO_TOOL_CALLS_SENTINEL}."
                            ),
                        })
                        continue
                    # Do not surface the sentinel to the user.
                    result = self._pending_final_content or ""
                    logger.debug(
                        "no_tools_ack agent=%s pending_chars=%d",
                        self.name, len(result),
                    )
                    return await self._finish_without_tools_async(result)

                # Candidate final prose — stream it, then demand an ack (or tools).
                if message.content:
                    self._emit_assistant_content(message.content)
                    self._pending_final_content = message.content

                self._no_tools_challenge_count += 1
                # After N failed no-tool turns (no real call, no NO_TOOL_CALLS), stop
                # challenging so we don't burn tokens forever.
                if self._no_tools_challenge_count >= self.no_tools_ack_max:
                    logger.warning(
                        "no_tools_ack_forced agent=%s attempts=%d",
                        self.name, self._no_tools_challenge_count,
                    )
                    result = self._pending_final_content or (message.content or "")
                    return await self._finish_without_tools_async(result)

                logger.debug(
                    "no_tools_ack_challenge agent=%s n=%d/%d",
                    self.name, self._no_tools_challenge_count, self.no_tools_ack_max,
                )
                self._history.append({"role": "user", "content": self.no_tools_ack_message})
                continue

            # Default exit: no tool calls and no tools used this run.
            # Never surface the NO_TOOL_CALLS sentinel even if the model still emits it.
            if _is_no_tools_ack(message.content):
                result = self._pending_final_content or ""
                return await self._finish_without_tools_async(result)
            if message.content:
                self._emit_assistant_content(message.content)
                self._pending_final_content = message.content
            result = self._pending_final_content or (message.content or "")
            return await self._finish_without_tools_async(result)
