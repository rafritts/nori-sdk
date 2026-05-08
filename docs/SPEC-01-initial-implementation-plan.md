# SPEC-01: Initial Implementation Plan

Each step is a discrete unit of work. Nothing moves forward until the current step is tested with real tokens and signed off.

Tests use real API calls — no mocks.

Unit tests live in `tests/unit/` and run without API keys. Integration tests live in `tests/integration/` and require real tokens.

---

## Architecture — Option B

Agent shell with internal modules. SRP where clean, pragmatic where forcing it creates ceremony.

```
nori/
  __init__.py              # exports: Agent, tool, ContextFile, ContextRole,
                           #          CheckpointScrutiny
  agent.py                 # Agent: public API, config, loop orchestration
  completer.py             # wraps AsyncOpenAI, single _complete() coroutine
  tool_registry.py         # registers tools, builds schemas, resolves call → fn
  tool_executor.py         # executes tools concurrently via asyncio.gather
  narrator.py              # on_narration / on_tool_result, default formatter
  context.py               # history, running summary, compaction (owns both)
  permissions.py           # allow/deny enforcement
  anti_spin.py             # checkpoint evaluation, AntiSpinTerminated
  pricing.py               # ModelPricing table, cost/token calculation
  tool.py                  # @tool decorator, reason injection, schema generation
  exceptions.py            # MaxTurnsExceeded, AntiSpinTerminated, PermissionError

  tools/
    __init__.py
    base.py                # BaseTool, .bind()
    bash.py
    file_edit.py
    file_search.py
    web_client.py
    code_runner.py
    bash_agent.py
    file_edit_agent.py
    file_search_agent.py
    web_agent.py
    web_search.py
    code_runner_agent.py
    compact.py
    self_modify/
      __init__.py
      custodian.py
      modify.py
      mutation.py

  mcp/
    __init__.py
    server.py              # MCPServer dataclass
    connector.py           # connects, discovers schemas, injects reason
    servers/
      __init__.py
      github.py
      filesystem.py
      postgres.py
      sqlite.py
      slack.py
      brave_search.py
```

**Single responsibilities:**
- `agent.py` — public API and loop orchestration. Allowed to know the loop exists.
- `completer.py` — one job: talk to AsyncOpenAI
- `tool_registry.py` — knows what tools exist and how to call them
- `tool_executor.py` — knows how to run tools concurrently
- `narrator.py` — knows how to emit narration (also logs to `nori.narration`)
- `context.py` — owns history mutations and compaction together (pragmatic)
- `permissions.py` — enforces allow/deny, nothing else
- `anti_spin.py` — checkpoint logic, nothing else
- `pricing.py` — token counting and cost math, nothing else
- `tool.py` — decorator, schema generation, reason injection

---

## Step 1 — Package scaffold

Create the `nori/` package and install dependencies.

**Files:**
- `nori/__init__.py`
- `nori/agent.py` (empty stub)
- `nori/tools/__init__.py` (empty stub)

**Dependencies to add:**
- `openai`
- `pydantic`

**Verify:** `from nori import Agent` imports without error. No API calls yet.

**Unit tests** (`tests/unit/test_scaffold.py`):
- `test_agent_importable` — `from nori import Agent` does not raise
- `test_agent_instantiable` — `Agent()` returns an instance

---

## Step 2 — `@tool` decorator

Introspect a function's name, docstring, and type annotations to build an OpenAI-compatible tool schema. Inject `reason: str` as a required parameter. Strip `reason` before calling the underlying function.

**Files:**
- `nori/tool.py`

**Verify:**
```python
@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return "sunny"

assert get_weather.schema["function"]["name"] == "get_weather"
assert "reason" in get_weather.schema["function"]["parameters"]["required"]
assert "city" in get_weather.schema["function"]["parameters"]["required"]
```

No API calls yet.

**Unit tests** (`tests/unit/test_tool.py`):
- `test_schema_name` — `schema["function"]["name"]` matches the function name
- `test_schema_description` — `schema["function"]["description"]` matches the docstring
- `test_reason_in_required` — `"reason"` is in `parameters["required"]`
- `test_user_param_in_required` — decorated function's params are in `required`
- `test_reason_stripped_before_call` — calling the wrapped fn with `reason=` does not pass it to the underlying function
- `test_type_mapping` — `str` → `"string"`, `int` → `"integer"`, `float` → `"number"`, `bool` → `"boolean"`
- `test_summarize_output_flag_default_true` — `get_weather.summarize_output is True`
- `test_summarize_output_flag_false` — `@tool(summarize_output=False)` sets `fn.summarize_output = False`
- `test_return_type_excluded_from_schema` — return annotation does not appear in `parameters`

---

## Step 3 — Single completion call

`Agent` constructor accepts `name`, `model`, `system_prompt`, `api_key`, `base_url`, `context_files`. Implement a raw `_complete()` coroutine that sends a message list to `AsyncOpenAI` and returns the response. `system_prompt` maps to the `system` role message. `ContextRole.SYSTEM` files are appended to it; `ContextRole.USER` and `ContextRole.ASSISTANT` files are prepended to the conversation history.

**Files:**
- `nori/agent.py`

**Verify:** Send a single `"Say hello."` message and print the response. Real API call.

**Unit tests** (`tests/unit/test_completer.py`):
- `test_system_prompt_maps_to_system_role` — mock `AsyncOpenAI`; assert first message has `role="system"` and `content=system_prompt`
- `test_context_role_system_appended_to_system_message` — `ContextRole.SYSTEM` file content is appended to the system message
- `test_context_role_user_prepended_to_history` — `ContextRole.USER` file appears before the user prompt in message list
- `test_context_role_assistant_prepended_to_history` — `ContextRole.ASSISTANT` file appears before the user prompt
- `test_returns_response_text` — mock returns a chat completion; assert `_complete()` returns the message content string

---

## Step 4 — Basic tool-calling loop

Implement `agent.run(prompt)`. Loop: call `_complete()`, check for tool calls, execute them sequentially (no parallelism yet), append results, repeat until no tool calls. Return final response text.

**Files:**
- `nori/agent.py`

**Verify:** Agent with `get_weather` tool, prompt `"What's the weather in Austin?"`. Confirm the loop runs, the tool fires, and a final response is returned. Real tokens.

**Unit tests** (`tests/unit/test_loop.py`):
- `test_loop_terminates_without_tool_calls` — mock `_complete()` returns text only; assert `run()` returns that text
- `test_tool_call_dispatched` — mock `_complete()` returns one tool call then text; assert the tool function was called
- `test_tool_result_appended_to_history` — after tool call, history contains a `role="tool"` message with the result
- `test_loop_iterates_until_no_tool_calls` — mock two rounds of tool calls before final text; assert loop ran three times
- `test_max_turns_raises` — set `max_turns=2`, mock loop that never stops; assert `MaxTurnsExceeded` raised

---

## Step 5 — Parallel tool execution

Replace sequential tool execution with `asyncio.gather`. Multiple tool calls in a single turn run concurrently.

**Files:**
- `nori/agent.py`

**Verify:** Agent with two tools, prompt that forces both to be called in one turn. Confirm both fire concurrently. Real tokens.

**Unit tests** (`tests/unit/test_loop.py`):
- `test_parallel_tools_both_called` — mock `_complete()` returns two tool calls; assert both tool functions were called
- `test_parallel_results_both_appended` — both `role="tool"` messages appear in history after one turn
- `test_parallel_execution_uses_gather` — patch `asyncio.gather`; assert it is called with both coroutines in one shot

---

## Step 6 — Narration

Fire `on_narration` from two sources: tool call `reason` fields (before each tool executes) and turn text content (when text accompanies tool calls). Default formatter: `{narrator_prefix}tool_name[reason]` printed to stdout.

**Files:**
- `nori/agent.py`

**Verify:** Run the step 4 scenario with `narration=True`. Confirm narration lines print before tool execution. Confirm custom `on_narration` callback fires with the formatted string.

**Unit tests** (`tests/unit/test_narration.py`):
- `test_on_narration_fires_before_tool_execution` — assert callback called before mock tool function
- `test_default_format_includes_tool_name_and_reason` — default formatter produces `"tool_name[reason text]"`
- `test_narrator_prefix_prepended` — with `narrator_prefix=">> "`, output starts with `">> "`
- `test_narration_from_text_content` — when completion returns text alongside tool calls, that text is passed to `on_narration`
- `test_narration_false_does_not_fire` — `narration=False` (default); callback never called
- `test_custom_callback_receives_string` — custom `on_narration` lambda receives a string argument

---

## Step 7 — `Bash` tool (native)

Sandboxed subprocess execution. Returns stdout + stderr. Required `reason` param built in.

**Files:**
- `nori/tools/bash.py`

**Verify:** Agent with `Bash`, prompt `"What files are in the current directory?"`. Confirm `ls` runs and the result reaches the model. Real tokens.

**Unit tests** (`tests/unit/test_tools.py`):
- `test_bash_stdout_returned` — mock `subprocess.run`; assert stdout is in the return value
- `test_bash_stderr_returned` — mock returns stderr; assert it is included in the return value
- `test_bash_reason_not_passed_to_subprocess` — assert the `command` arg to subprocess does not contain `reason`
- `test_bash_schema_has_reason_required` — `"reason"` in `Bash.schema["function"]["parameters"]["required"]`

---

## Step 8 — `FileEdit` tool (native)

Apply a patch to a file (read, replace, write).

**Files:**
- `nori/tools/file_edit.py`

**Verify:** Agent edits a temp file. Confirm the change is written to disk. Real tokens.

**Unit tests** (`tests/unit/test_tools.py`):
- `test_file_edit_replaces_content` — write a temp file; call tool; assert new content on disk
- `test_file_edit_missing_old_content_raises` — `old_content` not found in file raises a clear error
- `test_file_edit_reason_not_written_to_file` — file content does not contain the reason string

---

## Step 9 — `FileSearch` tool (native)

Find files by name or grep for content.

**Files:**
- `nori/tools/file_search.py`

**Verify:** Agent searches for a string across a temp directory. Confirm correct files are returned. Real tokens.

**Unit tests** (`tests/unit/test_tools.py`):
- `test_file_search_finds_by_name` — create temp files; search by name pattern; assert correct paths returned
- `test_file_search_finds_by_content` — create temp file with known content; grep for it; assert file returned
- `test_file_search_no_match_returns_empty` — search for string that doesn't exist; assert empty result

---

## Step 10 — `WebClient` tool (native)

Single HTTP request via `httpx`. Returns response body.

**Files:**
- `nori/tools/web_client.py`

**Verify:** Agent fetches a public URL and summarizes the response. Real tokens.

**Unit tests** (`tests/unit/test_tools.py`):
- `test_web_client_returns_response_body` — mock `httpx.AsyncClient.get`; assert body string returned
- `test_web_client_http_error_returns_status` — mock returns 404; assert error communicated in return value (not an unhandled exception)
- `test_web_client_method_passed_through` — POST with body; assert httpx called with correct method and body

---

## Step 11 — `CodeRunner` tool (native)

Execute a Python 3 snippet via subprocess. Returns stdout.

**Files:**
- `nori/tools/code_runner.py`

**Verify:** Agent with `CodeRunner`, prompt that requires a simple calculation. Confirm the snippet runs and stdout is returned. Real tokens.

**Unit tests** (`tests/unit/test_tools.py`):
- `test_code_runner_stdout_returned` — mock `subprocess.run`; assert stdout in return value
- `test_code_runner_exception_returned_not_raised` — mock subprocess raises; assert error text returned instead of propagating
- `test_code_runner_reason_not_in_snippet` — subprocess `args` does not include reason string

---

## Step 12 — Result summarization

After a tool returns, run a separate summarization pass before appending the result to the conversation. Pass the tool call's `reason` as the summarization hint. Opt out per-tool with `@tool(summarize_output=False)`.

**Files:**
- `nori/summarizer.py`
- `nori/agent.py` (wire in)

**Verify:** Run `Bash` with a command that returns large output. Confirm the appended tool result is a summary. Confirm `summarize_output=False` skips the pass. Real tokens.

**Unit tests** (`tests/unit/test_summarizer.py`):
- `test_reason_passed_as_hint` — mock LLM call; assert `reason` string appears in the summarization prompt
- `test_summarized_content_appended` — mock summarizer returns `"summary"`; assert history contains `"summary"`, not raw output
- `test_summarize_output_false_skips_summarizer` — tool with `summarize_output=False`; assert summarizer LLM never called
- `test_short_output_still_summarized` — summarization runs regardless of output length (no length gate)

---

## Step 13 — Running context summary

After each turn, maintain a rolling summary of what the agent has done. Inject it as a user-role message at the top of the conversation. Enable with `running_context_summary=True`.

**Files:**
- `nori/context.py`
- `nori/agent.py` (wire in)

**Verify:** Run a multi-turn task. Inspect `agent.history` and confirm the summary message is present and updates each turn. Real tokens.

**Unit tests** (`tests/unit/test_context.py`):
- `test_summary_injected_at_top_of_history` — after one turn with `running_context_summary=True`, history[0] is the summary message
- `test_summary_updates_each_turn` — mock LLM summary call; run two turns; assert summary message updated both times
- `test_disabled_by_default` — `running_context_summary=False` (default); no summary message in history
- `test_summary_role_is_user` — injected summary message has `role="user"`

---

## Step 14 — Autocompaction

Inject a warning message at 70% context fill. Force compaction at 85% — summarize history into the running summary, drop raw turns. Agent can call `Compact` tool voluntarily before threshold.

**Files:**
- `nori/tools/compact.py`
- `nori/agent.py` (wire in threshold checks)

**Verify:** Artificially lower the threshold to trigger compaction. Confirm warning fires at 70%, compaction fires at 85%, history is replaced with summary. Real tokens.

**Unit tests** (`tests/unit/test_context.py`):
- `test_warning_injected_at_70_percent` — set context fill to 71%; assert warning message injected into history
- `test_compaction_fires_at_85_percent` — set context fill to 86%; assert compaction runs (mock summarizer)
- `test_history_replaced_after_compaction` — after compaction, raw turns are gone; summary message is present
- `test_compact_tool_triggers_compaction` — calling `Compact` tool directly triggers the same compaction path
- `test_warning_not_injected_twice` — warning message appears at most once per compaction cycle

---

## Step 15 — QoL properties

Read-only properties on `Agent`: `context_length`, `token_counts`, `cost`, `turn_count`, `history`, `tool_calls`. `reset()` method. `cost` uses a hardcoded `ModelPricing` table.

**Files:**
- `nori/pricing.py`
- `nori/agent.py` (wire in)

**Verify:** Run any previous scenario. Assert all properties return sensible values. No API calls needed — deterministic computation.

**Unit tests** (`tests/unit/test_agent_properties.py`):
- `test_turn_count_increments` — mock loop; assert `turn_count` increments after each turn
- `test_token_counts_returns_dict` — assert `token_counts` has `prompt` and `completion` keys
- `test_cost_is_float` — assert `cost` returns a float
- `test_history_returns_list` — assert `history` is a list
- `test_tool_calls_returns_list` — assert `tool_calls` is a list
- `test_reset_clears_history_and_counters` — call `reset()`; assert history is empty, turn_count is 0
- `test_properties_are_read_only` — assigning to `history`, `cost`, etc. raises `AttributeError`
- `test_model_pricing_lookup` — `ModelPricing` returns correct per-token cost for a known model

---

## Step 16 — Permissions

`allow` and `deny` lists on `Agent`. Glob matching on tool names. Declaring both raises `RuntimeError` at construction. Calling a denied tool raises `PermissionError`.

**Files:**
- `nori/permissions.py`
- `nori/agent.py` (wire in)

**Verify:** Agent with `deny=["bash"]` attempts to call `Bash`. Confirm `PermissionError` is raised. Confirm `allow` list blocks unlisted tools. No extra API calls needed.

**Unit tests** (`tests/unit/test_permissions.py`):
- `test_allow_and_deny_raises_at_construction` — `Agent(allow=[...], deny=[...])` raises `RuntimeError`
- `test_denied_tool_raises_permission_error` — tool in `deny` list raises `PermissionError` when called
- `test_allowed_tool_executes` — tool in `allow` list executes without error
- `test_unlisted_tool_blocked_by_allow` — tool not in `allow` list raises `PermissionError`
- `test_glob_deny` — `deny=["bash*"]` blocks both `bash` and `bash_agent`
- `test_glob_allow` — `allow=["file*"]` permits `file_edit` and `file_search`, blocks `bash`

---

## Step 17 — `BashAgent` tool (agentic)

Spins up a sub-`Agent` with an isolated context window for multi-step shell work. Returns a summarized result.

**Files:**
- `nori/tools/bash_agent.py`

**Verify:** Agent with `BashAgent`, prompt requiring multi-step shell work. Confirm sub-loop runs, result is summarized, main context stays clean. Real tokens.

**Unit tests** (`tests/unit/test_tools.py`):
- `test_bash_agent_creates_sub_agent` — mock `Agent`; assert a new Agent is instantiated per call
- `test_bash_agent_result_returned` — mock sub-agent returns a result; assert it is the tool's return value
- `test_bash_agent_does_not_pollute_parent_history` — parent history unchanged after `BashAgent` call

---

## Step 18 — `FileEditAgent` tool (agentic)

Sub-agent for complex edits spanning many files.

**Files:**
- `nori/tools/file_edit_agent.py`

**Verify:** Agent with `FileEditAgent`, prompt requiring edits across multiple temp files. Confirm all edits applied, result summarized. Real tokens.

**Unit tests** (`tests/unit/test_tools.py`):
- `test_file_edit_agent_creates_sub_agent` — mock `Agent`; assert new Agent instantiated
- `test_file_edit_agent_result_returned` — mock sub-agent result returned correctly
- `test_file_edit_agent_isolated_context` — parent history unchanged after call

---

## Step 19 — `FileSearchAgent` tool (agentic)

Sub-agent for deep search requiring reasoning across results.

**Files:**
- `nori/tools/file_search_agent.py`

**Verify:** Agent with `FileSearchAgent`, prompt requiring multi-step search and reasoning. Confirm result is summarized. Real tokens.

**Unit tests** (`tests/unit/test_tools.py`):
- `test_file_search_agent_creates_sub_agent` — mock `Agent`; assert new Agent instantiated
- `test_file_search_agent_result_returned` — mock sub-agent result returned correctly
- `test_file_search_agent_isolated_context` — parent history unchanged after call

---

## Step 20 — `WebAgent` tool (agentic)

Sub-agent for multi-step web interaction, scraping, and research.

**Files:**
- `nori/tools/web_agent.py`

**Verify:** Agent with `WebAgent`, multi-step research prompt. Confirm result is summarized. Real tokens.

**Unit tests** (`tests/unit/test_tools.py`):
- `test_web_agent_creates_sub_agent` — mock `Agent`; assert new Agent instantiated
- `test_web_agent_result_returned` — mock sub-agent result returned correctly
- `test_web_agent_isolated_context` — parent history unchanged after call

---

## Step 21 — `WebSearch` tool (agentic)

Synthesized web search via sub-loop. No native counterpart.

**Files:**
- `nori/tools/web_search.py`

**Verify:** Agent with `WebSearch`, research prompt. Confirm synthesized result returned. Real tokens.

**Unit tests** (`tests/unit/test_tools.py`):
- `test_web_search_creates_sub_agent` — mock `Agent`; assert new Agent instantiated
- `test_web_search_result_returned` — mock sub-agent result returned correctly
- `test_web_search_isolated_context` — parent history unchanged after call

---

## Step 22 — `CodeRunnerAgent` tool (agentic)

First-class Python execution sub-agent: structured output, exception handling, multi-step coding tasks.

**Files:**
- `nori/tools/code_runner_agent.py`

**Verify:** Agent with `CodeRunnerAgent`, prompt requiring iterative code execution and reasoning. Confirm structured result returned, exceptions handled. Real tokens.

**Unit tests** (`tests/unit/test_tools.py`):
- `test_code_runner_agent_creates_sub_agent` — mock `Agent`; assert new Agent instantiated
- `test_code_runner_agent_result_returned` — mock sub-agent result returned correctly
- `test_code_runner_agent_isolated_context` — parent history unchanged after call

---

## Step 23 — Agents as tools

`Agent` implements the tool interface: `name`, `description` (falls back to `system_prompt` if not set), and `__call__`. Any `Agent` can be passed into another agent's `tools=[]`. The child agent runs its full loop in an isolated context window and returns a summarized result. The `reason` requirement applies — the parent agent must supply one.

**Files:**
- `nori/agent.py` (implement tool interface)

**Verify:** Two agents — a `Researcher` and a `Coder` — registered as tools on an `Orchestrator`. Prompt that requires both to be called. Confirm each sub-agent runs its own loop, results are summarized, orchestrator history stays clean. Real tokens.

**Unit tests** (`tests/unit/test_agent_as_tool.py`):
- `test_agent_has_name` — `Agent(name="Researcher", ...).name == "Researcher"`
- `test_description_falls_back_to_system_prompt` — agent with no `description` uses `system_prompt` as description
- `test_agent_schema_has_reason` — `"reason"` in agent's tool schema required params
- `test_agent_callable` — `await agent("do something", reason="...")` does not raise (mock the internal loop)
- `test_child_agent_isolated_context` — calling one agent as a tool does not append to the parent's history

---

## Step 24 — Bound tools

`.bind()` on any built-in tool. Locks specified params, sets overridable defaults. Returns a new tool object compatible with `tools=[]`.

**Files:**
- `nori/tools/base.py` (`.bind()` on base tool class)

**Verify:** `FileSearch.bind(path="/tmp")`. Confirm model cannot override `path`. Confirm optional params are overridable. Real tokens.

**Unit tests** (`tests/unit/test_bind.py`):
- `test_bind_returns_new_tool_instance` — `FileSearch.bind(path="/tmp")` is not `FileSearch`
- `test_locked_param_removed_from_schema` — `path` not in bound tool's schema parameters
- `test_locked_param_value_used_at_call_time` — calling bound tool without `path` uses the bound value
- `test_model_cannot_override_locked_param` — passing `path` at call time raises or is silently ignored
- `test_unbound_params_still_in_schema` — other params still appear and are overridable

---

## Step 25 — Anti-spin

`checkpoint=N` fires every N turns. Two isolated LLM calls: summarize recent turns, evaluate progress. `CheckpointScrutiny.STRICT/MODERATE/LENIENT` tunes the evaluation prompt. Raises `AntiSpinTerminated` on spin detection. `checkpoint_compact=True` replaces turns with summary on pass.

**Files:**
- `nori/anti_spin.py`
- `nori/agent.py` (wire in)

**Verify:** Agent in a contrived spin loop. Confirm `AntiSpinTerminated` raised at checkpoint. Confirm `checkpoint_compact=True` replaces turns. Real tokens.

**Unit tests** (`tests/unit/test_anti_spin.py`):
- `test_checkpoint_fires_every_n_turns` — mock evaluator; assert it is called at turn N, 2N, 3N
- `test_antispinterminated_raised_on_spin` — mock evaluator returns "spin detected"; assert `AntiSpinTerminated` raised
- `test_no_exception_on_progress` — mock evaluator returns "making progress"; assert loop continues
- `test_strict_scrutiny_prompt_differs_from_lenient` — assert evaluation prompt text differs by scrutiny level
- `test_checkpoint_compact_replaces_turns_on_pass` — mock pass; assert turns replaced with summary in history

---

## Step 26 — MCP integration

`MCPServer` class with `name`, `command`/`args`/`env` (stdio) or `url` (HTTP/SSE). `mcp_servers=[]` on `Agent`. `add_mcp_server()` / `remove_mcp_server()`. Nori injects `reason` into discovered tool schemas.

**Files:**
- `nori/mcp/__init__.py`
- `nori/mcp/server.py`
- `nori/agent.py` (wire in)

**Verify:** Agent with a local stdio MCP server. Confirm tools are discovered, `reason` is injected, and a tool call succeeds. Real tokens.

**Unit tests** (`tests/unit/test_mcp.py`):
- `test_mcpserver_stdio_construction` — `MCPServer(name="x", command="npx", args=[...])` stores fields correctly
- `test_mcpserver_url_construction` — `MCPServer(name="x", url="http://...")` stores fields correctly
- `test_reason_injected_into_discovered_schema` — mock discovered schema without `reason`; assert `reason` added to required
- `test_add_mcp_server` — after `agent.add_mcp_server(s)`, server is in `agent.mcp_servers`
- `test_remove_mcp_server` — after `agent.remove_mcp_server("name")`, server is removed

---

## Step 27 — Curated MCP server factories

Pre-built `MCPServer` factories in `nori.mcp.servers`: `GitHub`, `Filesystem`, `Postgres`, `SQLite`, `Slack`, `BraveSearch`.

**Files:**
- `nori/mcp/servers/github.py`
- `nori/mcp/servers/filesystem.py`
- `nori/mcp/servers/postgres.py`
- `nori/mcp/servers/sqlite.py`
- `nori/mcp/servers/slack.py`
- `nori/mcp/servers/brave_search.py`

**Verify:** Each factory returns a correctly configured `MCPServer`. Confirm at least one connects and exposes tools. Real tokens.

**Unit tests** (`tests/unit/test_mcp_servers.py`):
- `test_github_returns_mcpserver` — `GitHub(token="x")` returns an `MCPServer` instance
- `test_filesystem_returns_mcpserver` — `Filesystem(path="/tmp")` returns an `MCPServer` instance
- `test_postgres_returns_mcpserver` — `Postgres(connection_string="x")` returns an `MCPServer` instance
- `test_sqlite_returns_mcpserver` — `SQLite(db_path="/tmp/x.db")` returns an `MCPServer` instance
- `test_slack_returns_mcpserver` — `Slack(token="x")` returns an `MCPServer` instance
- `test_brave_search_returns_mcpserver` — `BraveSearch(api_key="x")` returns an `MCPServer` instance
- `test_factory_fields_populated` — each factory sets `name`, `command`/`args` or `url` correctly

---

## Step 28 — Self-modification tiers

`self_custodian`, `self_modify`, `self_mutation` constructor kwargs and runtime properties. Each tier unlocks a set of meta-tools. Tiers are additive.

**Files:**
- `nori/tools/self_modify/custodian.py`
- `nori/tools/self_modify/modify.py`
- `nori/tools/self_modify/mutation.py`

**Verify:** Agent with `self_custodian=True` calls `update_system_prompt()`. Confirm system prompt updates mid-run. Real tokens.

**Unit tests** (`tests/unit/test_self_modify.py`):
- `test_custodian_false_by_default` — `Agent()` does not expose custodian meta-tools
- `test_custodian_unlocks_update_system_prompt` — `Agent(self_custodian=True)` includes `update_system_prompt` in available tools
- `test_self_modify_additive` — `Agent(self_modify=True)` includes both custodian and modify tools
- `test_self_mutation_additive` — `Agent(self_mutation=True)` includes all three tiers
- `test_update_system_prompt_changes_system_prompt` — call `update_system_prompt` tool; assert `agent.system_prompt` updated

---

## Step 29 — Logging

Wire `nori.agent` and `nori.narration` loggers throughout. All agent activity logged at appropriate levels.

**Files:**
- `nori/agent.py` (wire in throughout)

**Verify:** Run any previous scenario with `logging.DEBUG` enabled on both loggers. Confirm output is structured and useful.

**Unit tests** (`tests/unit/test_logging.py`):
- `test_nori_agent_logger_exists` — `logging.getLogger("nori.agent")` is the logger used in `agent.py`
- `test_nori_narration_logger_exists` — `logging.getLogger("nori.narration")` is used for narration events
- `test_tool_call_logged_at_debug` — mock logger; assert DEBUG record emitted when a tool is called
- `test_narration_logged` — narration events emit to `nori.narration` logger
- `test_error_logged_on_tool_failure` — tool raising an exception emits an ERROR record
