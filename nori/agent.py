import asyncio
import json
import logging
import uuid

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessage

from nori.anti_spin import CheckpointScrutiny, evaluate_checkpoint
import nori.config as config
from nori.context import ContextFile, ContextRole, inject_summary, update_running_summary
from nori.exceptions import AntiSpinTerminated, MaxTurnsExceeded
from nori.mcp.server import MCPServer
from nori.permissions import PermissionGuard
from nori.pricing import cost_for
from nori.summarizer import summarize

logger = logging.getLogger("nori.agent")
narration_logger = logging.getLogger("nori.narration")

_COMPACT_WARNING = (
    "[System] Context window is 70% full. Consider wrapping up or calling Compact."
)
_COMPACT_MARKER = "__compact_warning__"


class Agent:
    def __init__(
        self,
        name: str,
        model: str = None,
        system_prompt: str = "",
        api_key: str = None,
        base_url: str = None,
        context_files: list[ContextFile] = None,
        tools: list = None,
        max_turns: int | None = 10,
        allow: list[str] = None,
        deny: list[str] = None,
        description: str = "",
        checkpoint: int | None = None,
        checkpoint_scrutiny: CheckpointScrutiny = CheckpointScrutiny.MODERATE,
        checkpoint_compact: bool = False,
        self_custodian: bool = False,
        self_modify: bool = False,
        self_mutation: bool = False,
    ):
        self.name = name
        self.model = model or config.DEFAULT_MODEL
        self.system_prompt = system_prompt
        self.description = description
        self._context_files = context_files or []
        self._api_key = api_key or config.API_KEY
        self._base_url = base_url or config.BASE_URL
        self.__client: AsyncOpenAI | None = None
        self._tools: dict = {self._tool_name(t): t for t in (tools or [])}
        self._permissions = PermissionGuard(allow, deny)
        self._max_turns = max_turns
        self._history: list[dict] = []
        self._turn_count = 0
        self.narration: bool = False
        self.narrator_prefix: str = ""
        self.on_narration = self._default_narrator
        self.on_tool_result = self._default_tool_result_handler
        self.summarize_tool_output: bool = True
        self.running_context_summary: bool = False
        self._running_summary: str = ""
        self.max_context_chars: int = 200_000
        self._compact_warning_injected: bool = False
        self._mcp_servers: list[MCPServer] = []
        self.self_custodian = self_custodian
        self.self_modify = self_modify
        self.self_mutation = self_mutation
        if self_custodian or self_modify or self_mutation:
            self._register_self_modify_tools(self_custodian, self_modify, self_mutation)
        self._checkpoint = checkpoint
        self._checkpoint_scrutiny = checkpoint_scrutiny
        self._checkpoint_compact = checkpoint_compact
        self._prompt_tokens: int = 0
        self._completion_tokens: int = 0
        self._tool_calls_log: list[dict] = []
        self.auditor = None
        self.narration_call_id: bool = True
        self.narration_trace_id: bool = False
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
            self.__client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        return self.__client

    # ── Self-modification ─────────────────────────────────────────────────────

    def _register_self_modify_tools(self, custodian: bool, modify: bool, mutation: bool) -> None:
        from nori.tools.self_modify.custodian import make_custodian_tools
        from nori.tools.self_modify.modify import make_modify_tools
        from nori.tools.self_modify.mutation import make_mutation_tools

        for t in make_custodian_tools(self):
            self._tools[self._tool_name(t)] = t
        if modify or mutation:
            for t in make_modify_tools(self):
                self._tools[self._tool_name(t)] = t
        if mutation:
            for t in make_mutation_tools(self):
                self._tools[self._tool_name(t)] = t

    # ── MCP ───────────────────────────────────────────────────────────────────

    @property
    def mcp_servers(self) -> list[MCPServer]:
        return self._mcp_servers

    def add_mcp_server(self, server: MCPServer) -> None:
        self._mcp_servers.append(server)

    def remove_mcp_server(self, name: str) -> None:
        self._mcp_servers = [s for s in self._mcp_servers if s.name != name]

    @staticmethod
    def _inject_reason_into_schema(schema: dict) -> dict:
        """Ensure a discovered MCP tool schema has 'reason' in its required params."""
        import copy
        schema = copy.deepcopy(schema)
        params = schema.get("function", {}).get("parameters", {})
        props = params.setdefault("properties", {})
        required = params.setdefault("required", [])
        if "reason" not in props:
            props["reason"] = {"type": "string", "description": "Your reason for calling this tool."}
        if "reason" not in required:
            required.append("reason")
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

    async def __call__(self, task: str, reason: str = "") -> str:
        sub = Agent(
            name=self.name,
            model=self.model,
            system_prompt=self.system_prompt,
            api_key=self._api_key,
            base_url=self._base_url,
            tools=list(self._tools.values()),
            max_turns=self._max_turns,
            description=self.description,
        )
        return await sub.run(task, _trace_id=self._trace_id, _parent_span_id=self._span_id)

    def _context_fill(self) -> float:
        total = sum(len(str(m.get("content", ""))) for m in self._history)
        return total / self.max_context_chars if self.max_context_chars else 0.0

    async def _compact(self) -> None:
        self._running_summary = await update_running_summary(
            self._history, self._running_summary, self._client, self.model
        )
        self._history = inject_summary(self._history, self._running_summary)
        self._compact_warning_injected = False

    def _default_narrator(self, text: str) -> None:
        print(text)

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
            msg = f"{self.narrator_prefix}{name_part}[{self._trace_id}]{suffix}"
        else:
            msg = f"{self.narrator_prefix}{name_part}{suffix}"

        narration_logger.debug(msg)
        if self.narration:
            self.on_narration(msg)

    def _narrate_result(self, tool_name: str, result: str, call_id: str | None, is_parallel: bool) -> None:
        if not self.narration or not is_parallel or not self.narration_call_id or not call_id:
            return
        flat = result.replace("\n", " | ")
        name_part = f"{tool_name}-{call_id}"
        if self.narration_trace_id and self._trace_id:
            msg = f"{self.narrator_prefix}{name_part}[{self._trace_id}][Result: {flat}]"
        else:
            msg = f"{self.narrator_prefix}{name_part}[Result: {flat}]"
        narration_logger.debug(msg)
        self.on_narration(msg)

    def _tool_name(self, t) -> str:
        return t.schema["function"]["name"]

    def _tool_schemas(self) -> list[dict]:
        return [t.schema for t in self._tools.values()]

    def _build_messages(self, history: list[dict]) -> list[dict]:
        system_content = self.system_prompt
        for cf in self._context_files:
            if cf.role == ContextRole.SYSTEM:
                system_content += "\n\n" + cf.content

        messages = [{"role": "system", "content": system_content}]

        for cf in self._context_files:
            if cf.role == ContextRole.USER:
                messages.append({"role": "user", "content": cf.content})
            elif cf.role == ContextRole.ASSISTANT:
                messages.append({"role": "assistant", "content": cf.content})

        messages.extend(history)
        return messages

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
        return d

    async def _invoke_tool(self, tc, is_parallel: bool = False) -> dict:
        if tc.function.name == "Compact":
            await self._compact()
            return {"role": "tool", "tool_call_id": tc.id, "content": "History compacted."}
        self._permissions.check(tc.function.name)
        fn = self._tools[tc.function.name]
        args = json.loads(tc.function.arguments)
        reason = args.get("reason", "")
        tool_span_id = uuid.uuid4().hex[:8]
        tool_call_id = tool_span_id[:4]
        self._narrate(tc.function.name, reason, tool_call_id, is_parallel)
        logger.debug("tool_call name=%s args=%s", tc.function.name, args)
        if self.auditor:
            self.auditor.tool_call(
                self.name, tc.function.name, args,
                trace_id=self._trace_id, span_id=tool_span_id,
                parent_span_id=self._span_id, call_id=tool_call_id,
            )
        try:
            result = await fn(**args)
        except Exception as exc:
            logger.error("tool_error name=%s error=%s", tc.function.name, exc)
            if self.auditor:
                self.auditor.tool_error(
                    self.name, tc.function.name, str(exc),
                    trace_id=self._trace_id, span_id=tool_span_id,
                    parent_span_id=self._span_id, call_id=tool_call_id,
                )
            raise
        content = str(result) or "[EMPTY]"
        if self.summarize_tool_output and getattr(fn, "summarize_output", True):
            content = await summarize(content, reason, self._client, self.model)
        logger.debug("tool_result name=%s result=%s", tc.function.name, content)
        self._narrate_result(tc.function.name, content, tool_call_id, is_parallel)
        if self.auditor:
            self.auditor.tool_result(
                self.name, tc.function.name, content,
                trace_id=self._trace_id, span_id=tool_span_id,
                parent_span_id=self._span_id, call_id=tool_call_id,
            )
        self._tool_calls_log.append({"name": tc.function.name, "args": args, "result": content})
        self.on_tool_result(tc.function.name, content, tool_call_id, self._trace_id)
        return {"role": "tool", "tool_call_id": tc.id, "content": content}

    async def _execute_tools(self, tool_calls) -> list[dict]:
        is_parallel = len(tool_calls) > 1
        return list(await asyncio.gather(*[self._invoke_tool(tc, is_parallel) for tc in tool_calls]))

    async def _complete(self, history: list[dict]) -> ChatCompletionMessage:
        messages = self._build_messages(history)
        kwargs: dict = {"model": self.model, "messages": messages}
        if self._tools:
            kwargs["tools"] = self._tool_schemas()
        response = await self._client.chat.completions.create(**kwargs)
        if response.usage:
            self._prompt_tokens += response.usage.prompt_tokens or 0
            self._completion_tokens += response.usage.completion_tokens or 0
        return response.choices[0].message

    # ── QoL properties ────────────────────────────────────────────────────────

    @property
    def history(self) -> list[dict]:
        return self._history

    @property
    def turn_count(self) -> int:
        return self._turn_count

    @property
    def token_counts(self) -> dict[str, int]:
        return {"prompt": self._prompt_tokens, "completion": self._completion_tokens}

    @property
    def cost(self) -> float:
        return cost_for(self.model, self._prompt_tokens, self._completion_tokens)

    @property
    def context_length(self) -> int:
        return self._prompt_tokens + self._completion_tokens

    @property
    def tool_calls(self) -> list[dict]:
        return self._tool_calls_log

    def reset(self) -> None:
        self._history = []
        self._turn_count = 0
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._tool_calls_log = []
        self._running_summary = ""
        self._compact_warning_injected = False
        self._trace_id = None
        self._span_id = None
        self.parent_span_id = None

    async def run(self, prompt: str, _trace_id: str | None = None, _parent_span_id: str | None = None) -> str:
        self._trace_id = _trace_id or str(uuid.uuid4())
        self._span_id = uuid.uuid4().hex[:8]
        if _parent_span_id:
            self.parent_span_id = _parent_span_id
        logger.debug("run agent=%s prompt=%r", self.name, prompt[:80])
        if self.auditor:
            self.auditor.agent_start(
                self.name, prompt,
                trace_id=self._trace_id, span_id=self._span_id,
                parent_span_id=self.parent_span_id,
            )
        self._history.append({"role": "user", "content": prompt})

        while True:
            if self._max_turns is not None and self._turn_count >= self._max_turns:
                raise MaxTurnsExceeded(f"Reached max_turns={self._max_turns}")

            message = await self._complete(self._history)
            self._turn_count += 1
            logger.debug("turn agent=%s turn=%d tool_calls=%d",
                         self.name, self._turn_count,
                         len(message.tool_calls) if message.tool_calls else 0)
            self._history.append(self._message_to_dict(message))

            fill = self._context_fill()
            if fill >= 0.85:
                await self._compact()
            elif fill >= 0.70 and not self._compact_warning_injected:
                self._history.append({
                    "role": "user",
                    "content": _COMPACT_WARNING,
                    "_marker": _COMPACT_MARKER,
                })
                self._compact_warning_injected = True

            if message.content and message.tool_calls and self.narration:
                self.on_narration(f"{self.narrator_prefix}{message.content}")

            if self._checkpoint and self._turn_count % self._checkpoint == 0:
                recent = self._history[-self._checkpoint * 4:]
                is_spin, summary = await evaluate_checkpoint(
                    recent, self._checkpoint_scrutiny, self._client, self.model
                )
                if is_spin:
                    raise AntiSpinTerminated(
                        f"Anti-spin triggered at turn {self._turn_count}. Summary: {summary}"
                    )
                if self._checkpoint_compact:
                    self._history = inject_summary(self._history, summary)

            if not message.tool_calls:
                if self.running_context_summary:
                    self._running_summary = await update_running_summary(
                        self._history, self._running_summary, self._client, self.model
                    )
                    self._history = inject_summary(self._history, self._running_summary)
                result = message.content or ""
                if self.auditor:
                    self.auditor.agent_end(
                        self.name, result, self._turn_count, self.cost,
                        trace_id=self._trace_id, span_id=self._span_id,
                        parent_span_id=self.parent_span_id,
                    )
                return result

            tool_results = await self._execute_tools(message.tool_calls)
            self._history.extend(tool_results)
