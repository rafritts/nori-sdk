# SPEC-01: Initial Implementation Plan

Each step is a discrete unit of work. Nothing moves forward until the current step is tested with real tokens and signed off.

Tests use real API calls — no mocks.

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

---

## Step 3 — Single completion call

`Agent` constructor accepts `name`, `model`, `system_prompt`, `api_key`, `base_url`, `context_files`. Implement a raw `_complete()` coroutine that sends a message list to `AsyncOpenAI` and returns the response. `system_prompt` maps to the `system` role message. `ContextRole.SYSTEM` files are appended to it; `ContextRole.USER` and `ContextRole.ASSISTANT` files are prepended to the conversation history.

**Files:**
- `nori/agent.py`

**Verify:** Send a single `"Say hello."` message and print the response. Real API call.

---

## Step 4 — Basic tool-calling loop

Implement `agent.run(prompt)`. Loop: call `_complete()`, check for tool calls, execute them sequentially (no parallelism yet), append results, repeat until no tool calls. Return final response text.

**Files:**
- `nori/agent.py`

**Verify:** Agent with `get_weather` tool, prompt `"What's the weather in Austin?"`. Confirm the loop runs, the tool fires, and a final response is returned. Real tokens.

---

## Step 5 — Parallel tool execution

Replace sequential tool execution with `asyncio.gather`. Multiple tool calls in a single turn run concurrently.

**Files:**
- `nori/agent.py`

**Verify:** Agent with two tools, prompt that forces both to be called in one turn. Confirm both fire concurrently. Real tokens.

---

## Step 6 — Narration

Fire `on_narration` from two sources: tool call `reason` fields (before each tool executes) and turn text content (when text accompanies tool calls). Default formatter: `{narrator_prefix}tool_name[reason]` printed to stdout.

**Files:**
- `nori/agent.py`

**Verify:** Run the step 4 scenario with `narration=True`. Confirm narration lines print before tool execution. Confirm custom `on_narration` callback fires with the formatted string.

---

## Step 7 — `Bash` tool (native)

Sandboxed subprocess execution. Returns stdout + stderr. Required `reason` param built in.

**Files:**
- `nori/tools/bash.py`

**Verify:** Agent with `Bash`, prompt `"What files are in the current directory?"`. Confirm `ls` runs and the result reaches the model. Real tokens.

---

## Step 8 — `FileEdit` tool (native)

Apply a patch to a file (read, replace, write).

**Files:**
- `nori/tools/file_edit.py`

**Verify:** Agent edits a temp file. Confirm the change is written to disk. Real tokens.

---

## Step 9 — `FileSearch` tool (native)

Find files by name or grep for content.

**Files:**
- `nori/tools/file_search.py`

**Verify:** Agent searches for a string across a temp directory. Confirm correct files are returned. Real tokens.

---

## Step 10 — `WebClient` tool (native)

Single HTTP request via `httpx`. Returns response body.

**Files:**
- `nori/tools/web_client.py`

**Verify:** Agent fetches a public URL and summarizes the response. Real tokens.

---

## Step 11 — `CodeRunner` tool (native)

Execute a Python 3 snippet via subprocess. Returns stdout.

**Files:**
- `nori/tools/code_runner.py`

**Verify:** Agent with `CodeRunner`, prompt that requires a simple calculation. Confirm the snippet runs and stdout is returned. Real tokens.

---

## Step 12 — Result summarization

After a tool returns, run a separate summarization pass before appending the result to the conversation. Pass the tool call's `reason` as the summarization hint. Opt out per-tool with `@tool(summarize_output=False)`.

**Files:**
- `nori/summarizer.py`
- `nori/agent.py` (wire in)

**Verify:** Run `Bash` with a command that returns large output. Confirm the appended tool result is a summary. Confirm `summarize_output=False` skips the pass. Real tokens.

---

## Step 13 — Running context summary

After each turn, maintain a rolling summary of what the agent has done. Inject it as a user-role message at the top of the conversation. Enable with `running_context_summary=True`.

**Files:**
- `nori/context.py`
- `nori/agent.py` (wire in)

**Verify:** Run a multi-turn task. Inspect `agent.history` and confirm the summary message is present and updates each turn. Real tokens.

---

## Step 14 — Autocompaction

Inject a warning message at 70% context fill. Force compaction at 85% — summarize history into the running summary, drop raw turns. Agent can call `Compact` tool voluntarily before threshold.

**Files:**
- `nori/tools/compact.py`
- `nori/agent.py` (wire in threshold checks)

**Verify:** Artificially lower the threshold to trigger compaction. Confirm warning fires at 70%, compaction fires at 85%, history is replaced with summary. Real tokens.

---

## Step 15 — QoL properties

Read-only properties on `Agent`: `context_length`, `token_counts`, `cost`, `turn_count`, `history`, `tool_calls`. `reset()` method. `cost` uses a hardcoded `ModelPricing` table.

**Files:**
- `nori/pricing.py`
- `nori/agent.py` (wire in)

**Verify:** Run any previous scenario. Assert all properties return sensible values. No API calls needed — deterministic computation.

---

## Step 16 — Permissions

`allow` and `deny` lists on `Agent`. Glob matching on tool names. Declaring both raises `RuntimeError` at construction. Calling a denied tool raises `PermissionError`.

**Files:**
- `nori/permissions.py`
- `nori/agent.py` (wire in)

**Verify:** Agent with `deny=["bash"]` attempts to call `Bash`. Confirm `PermissionError` is raised. Confirm `allow` list blocks unlisted tools. No extra API calls needed.

---

## Step 17 — `BashAgent` tool (agentic)

Spins up a sub-`Agent` with an isolated context window for multi-step shell work. Returns a summarized result.

**Files:**
- `nori/tools/bash_agent.py`

**Verify:** Agent with `BashAgent`, prompt requiring multi-step shell work. Confirm sub-loop runs, result is summarized, main context stays clean. Real tokens.

---

## Step 18 — `FileEditAgent` tool (agentic)

Sub-agent for complex edits spanning many files.

**Files:**
- `nori/tools/file_edit_agent.py`

**Verify:** Agent with `FileEditAgent`, prompt requiring edits across multiple temp files. Confirm all edits applied, result summarized. Real tokens.

---

## Step 19 — `FileSearchAgent` tool (agentic)

Sub-agent for deep search requiring reasoning across results.

**Files:**
- `nori/tools/file_search_agent.py`

**Verify:** Agent with `FileSearchAgent`, prompt requiring multi-step search and reasoning. Confirm result is summarized. Real tokens.

---

## Step 20 — `WebAgent` tool (agentic)

Sub-agent for multi-step web interaction, scraping, and research.

**Files:**
- `nori/tools/web_agent.py`

**Verify:** Agent with `WebAgent`, multi-step research prompt. Confirm result is summarized. Real tokens.

---

## Step 21 — `WebSearch` tool (agentic)

Synthesized web search via sub-loop. No native counterpart.

**Files:**
- `nori/tools/web_search.py`

**Verify:** Agent with `WebSearch`, research prompt. Confirm synthesized result returned. Real tokens.

---

## Step 22 — `CodeRunnerAgent` tool (agentic)

First-class Python execution sub-agent: structured output, exception handling, multi-step coding tasks.

**Files:**
- `nori/tools/code_runner_agent.py`

**Verify:** Agent with `CodeRunnerAgent`, prompt requiring iterative code execution and reasoning. Confirm structured result returned, exceptions handled. Real tokens.

---

## Step 23 — Agents as tools

`Agent` implements the tool interface: `name`, `description` (falls back to `system_prompt` if not set), and `__call__`. Any `Agent` can be passed into another agent's `tools=[]`. The child agent runs its full loop in an isolated context window and returns a summarized result. The `reason` requirement applies — the parent agent must supply one.

**Files:**
- `nori/agent.py` (implement tool interface)

**Verify:** Two agents — a `Researcher` and a `Coder` — registered as tools on an `Orchestrator`. Prompt that requires both to be called. Confirm each sub-agent runs its own loop, results are summarized, orchestrator history stays clean. Real tokens.

---

## Step 24 — Bound tools

`.bind()` on any built-in tool. Locks specified params, sets overridable defaults. Returns a new tool object compatible with `tools=[]`.

**Files:**
- `nori/tools/base.py` (`.bind()` on base tool class)

**Verify:** `FileSearch.bind(path="/tmp")`. Confirm model cannot override `path`. Confirm optional params are overridable. Real tokens.

---

## Step 25 — Anti-spin

`checkpoint=N` fires every N turns. Two isolated LLM calls: summarize recent turns, evaluate progress. `CheckpointScrutiny.STRICT/MODERATE/LENIENT` tunes the evaluation prompt. Raises `AntiSpinTerminated` on spin detection. `checkpoint_compact=True` replaces turns with summary on pass.

**Files:**
- `nori/anti_spin.py`
- `nori/agent.py` (wire in)

**Verify:** Agent in a contrived spin loop. Confirm `AntiSpinTerminated` raised at checkpoint. Confirm `checkpoint_compact=True` replaces turns. Real tokens.

---

## Step 26 — MCP integration

`MCPServer` class with `name`, `command`/`args`/`env` (stdio) or `url` (HTTP/SSE). `mcp_servers=[]` on `Agent`. `add_mcp_server()` / `remove_mcp_server()`. Nori injects `reason` into discovered tool schemas.

**Files:**
- `nori/mcp/__init__.py`
- `nori/mcp/server.py`
- `nori/agent.py` (wire in)

**Verify:** Agent with a local stdio MCP server. Confirm tools are discovered, `reason` is injected, and a tool call succeeds. Real tokens.

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

---

## Step 28 — Self-modification tiers

`self_custodian`, `self_modify`, `self_mutation` constructor kwargs and runtime properties. Each tier unlocks a set of meta-tools. Tiers are additive.

**Files:**
- `nori/tools/self_modify/custodian.py`
- `nori/tools/self_modify/modify.py`
- `nori/tools/self_modify/mutation.py`

**Verify:** Agent with `self_custodian=True` calls `update_system_prompt()`. Confirm system prompt updates mid-run. Real tokens.

---

## Step 29 — Logging

Wire `nori.agent` and `nori.narration` loggers throughout. All agent activity logged at appropriate levels.

**Files:**
- `nori/agent.py` (wire in throughout)

**Verify:** Run any previous scenario with `logging.DEBUG` enabled on both loggers. Confirm output is structured and useful.
