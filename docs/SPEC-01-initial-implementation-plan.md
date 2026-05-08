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

`Agent` constructor accepts `name`, `model`, `instructions`, `api_key`, `base_url`. Implement a raw `_complete()` coroutine that sends a message list to `AsyncOpenAI` and returns the response.

**Files:**
- `nori/agent.py`

**Verify:** Send a single `"Say hello."` message and print the response. Costs ~1 token. Real API call.

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

## Step 8 — `FileEdit` and `FileSearch` tools (native)

`FileEdit` — apply a patch to a file (read, replace, write).
`FileSearch` — find files by name or grep for content.

**Files:**
- `nori/tools/file_edit.py`
- `nori/tools/file_search.py`

**Verify:** Agent edits a temp file. Agent searches for a string across a temp directory. Real tokens.

---

## Step 9 — `WebClient` tool (native)

Single HTTP request via `httpx`. Returns response body.

**Files:**
- `nori/tools/web_client.py`

**Verify:** Agent fetches a public URL and summarizes the response. Real tokens.

---

## Step 10 — Result summarization

After a tool returns, run a separate summarization pass before appending the result to the conversation. Pass the tool call's `reason` as the summarization hint. Opt out per-tool with `@tool(summarize_output=False)`.

**Files:**
- `nori/summarizer.py`
- `nori/agent.py` (wire in)

**Verify:** Run `Bash` with a command that returns large output. Confirm the appended tool result is a summary, not the raw output. Confirm `summarize_output=False` skips the pass. Real tokens.

---

## Step 11 — Running context summary

After each turn, maintain a rolling summary of what the agent has done. Inject it as a user-role message at the top of the conversation. Enable with `running_context_summary=True`.

**Files:**
- `nori/context.py`
- `nori/agent.py` (wire in)

**Verify:** Run a multi-turn task. Inspect `agent.history` and confirm the summary message is present and updates each turn. Real tokens.

---

## Step 12 — Autocompaction

Inject a warning message at 70% context fill. Force compaction at 85% — summarize history into the running summary, drop raw turns. Agent can call `Compact` tool voluntarily before threshold.

**Files:**
- `nori/tools/compact.py`
- `nori/agent.py` (wire in threshold checks)

**Verify:** Artificially lower the threshold to trigger compaction. Confirm warning fires at 70%, compaction fires at 85%, history is replaced with summary. Real tokens.

---

## Step 13 — QoL properties

Read-only properties on `Agent`: `context_length`, `token_counts`, `cost`, `turn_count`, `history`, `tool_calls`. `reset()` method. `cost` uses a hardcoded `ModelPricing` table.

**Files:**
- `nori/pricing.py`
- `nori/agent.py` (wire in)

**Verify:** Run any previous test scenario. Assert all properties return sensible values. No API calls needed for this step — deterministic computation.

---

## Step 14 — Permissions

`allow` and `deny` lists on `Agent`. Glob matching on tool names. Declaring both raises `RuntimeError` at construction. Calling a denied tool raises `PermissionError`.

**Files:**
- `nori/permissions.py`
- `nori/agent.py` (wire in)

**Verify:** Agent with `deny=["bash"]` attempts to call `Bash`. Confirm `PermissionError` is raised. Confirm `allow` list blocks unlisted tools. No extra API calls needed.

---

## Step 15 — Agentic tools (`BashAgent`, `FileEditAgent`, `FileSearchAgent`, `WebAgent`)

Each agentic tool spins up a sub-`Agent` with an isolated context window, runs to completion, and returns a summarized result. Main agent never sees sub-loop history.

**Files:**
- `nori/tools/bash_agent.py`
- `nori/tools/file_edit_agent.py`
- `nori/tools/file_search_agent.py`
- `nori/tools/web_agent.py`

**Verify:** Agent with `BashAgent`, prompt requiring multi-step shell work. Confirm sub-loop runs, result is summarized, main context stays clean. Real tokens.

---

## Step 16 — `WebSearch` agentic tool

Synthesized web search via sub-loop. No native counterpart.

**Files:**
- `nori/tools/web_search.py`

**Verify:** Agent with `WebSearch`, research prompt. Real tokens.

---

## Step 17 — Bound tools

`.bind()` on any built-in tool. Locks specified params, sets overridable defaults. Returns a new tool object compatible with `tools=[]`.

**Files:**
- `nori/tools/base.py` (`.bind()` on base tool class)

**Verify:** `FileSearch.bind(path="/tmp")`. Confirm model cannot override `path`. Confirm optional params are overridable. Real tokens.

---

## Step 18 — Anti-spin

`checkpoint=N` fires every N turns. Two isolated LLM calls: summarize recent turns, evaluate progress. `CheckpointScrutiny.STRICT/MODERATE/LENIENT` tunes the evaluation prompt. Raises `AntiSpinTerminated` on spin detection. `checkpoint_compact=True` replaces turns with summary on pass.

**Files:**
- `nori/anti_spin.py`
- `nori/agent.py` (wire in)

**Verify:** Agent in a contrived spin loop. Confirm `AntiSpinTerminated` raised at checkpoint. Confirm `checkpoint_compact=True` replaces turns. Real tokens.

---

## Step 19 — MCP integration

`MCPServer` class with `name`, `command`/`args`/`env` (stdio) or `url` (HTTP/SSE). `mcp_servers=[]` on `Agent`. `add_mcp_server()` / `remove_mcp_server()`. Nori injects `reason` into discovered tool schemas.

**Files:**
- `nori/mcp/__init__.py`
- `nori/mcp/server.py`
- `nori/agent.py` (wire in)

**Verify:** Agent with a local stdio MCP server. Confirm tools are discovered, `reason` is injected, and a tool call succeeds. Real tokens.

---

## Step 20 — Curated MCP server factories

Pre-built `MCPServer` factories in `nori.mcp.servers`: `GitHub`, `Filesystem`, `Postgres`, `SQLite`, `Slack`, `BraveSearch`.

**Files:**
- `nori/mcp/servers.py`

**Verify:** `GitHub(token="...")` returns a correctly configured `MCPServer`. Confirm at least one factory connects and exposes tools. Real tokens.

---

## Step 21 — Self-modification tiers

`self_custodian`, `self_modify`, `self_mutation` constructor kwargs and runtime properties. Each tier unlocks a set of meta-tools. Tiers are additive.

**Files:**
- `nori/tools/self_modify.py`

**Verify:** Agent with `self_custodian=True` calls `update_instructions()`. Confirm system prompt updates mid-run. Real tokens.

---

## Step 22 — Logging

Wire `nori.agent` and `nori.narration` loggers throughout. All agent activity logged at appropriate levels.

**Files:**
- `nori/agent.py` (wire in throughout)

**Verify:** Run any previous scenario with `logging.DEBUG` enabled on both loggers. Confirm output is structured and useful.
