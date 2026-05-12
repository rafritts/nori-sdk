# Patterns

## Agents as tools

Any `Agent` instance exposes a `.schema` property and is callable, which makes it a first-class tool. Pass an agent into another agent's `tools=` list and the orchestrator can delegate to it just like any other tool.

```python
from nori import Agent
from nori.tool import tool

@tool
def web_lookup(query: str) -> str:
    """Look up a topic and return a brief factual summary."""
    ...

researcher = Agent(
    name="Researcher",
    description="Looks up factual information.",  # shown to the orchestrator
    system_prompt="You are a research agent. Use web_lookup to find facts.",
    tools=[web_lookup],
)

orchestrator = Agent(
    name="Orchestrator",
    system_prompt=(
        "You coordinate a Researcher and a Writer. "
        "Delegate research and formatting tasks appropriately."
    ),
    tools=[researcher, writer],
)

result = await orchestrator.run("Write a comparison of Python and Rust.")
```

The `description` field is what the orchestrator sees in the tool schema — make it specific so the model knows when to delegate.

See [`agent_as_tool_demo.py`](https://github.com/rafritts/nori/blob/master/demos/agent_as_tool_demo.py) for a full example with a researcher and writer working under an orchestrator.

---

## Parallel dispatch

When an orchestrator calls multiple sub-agents in the same turn, Nori executes them concurrently. The model decides to call several tools at once; Nori runs them in parallel automatically.

See [`parallel_demo.py`](https://github.com/rafritts/nori/blob/master/demos/parallel_demo.py) for a multi-agent parallel code review: three specialist reviewers (security, performance, correctness) dispatched simultaneously by an orchestrator, with B3 trace propagation across all four agents.

---

## Human-in-the-loop (HITL)

The `HumanInput` tool pauses the agent and waits for a human response before continuing. It requires the embedded server to be enabled.

```python
import nori
from nori import Agent
from nori.tools import HumanInput

nori.configure(server=True)

agent = Agent(
    name="CautiousAgent",
    system_prompt=(
        "You are a cautious assistant. Before taking any significant action, "
        "always use HumanInput to ask for approval."
    ),
    tools=[HumanInput],
)

result = await agent.run("Purge all log files older than 30 days from /var/log/app.")
```

The agent hits `HumanInput`, posts a question to `GET /hitl/pending`, and waits. Your application responds via `POST /hitl/{id}/respond` with the human's answer.

See [`hitl_demo.py`](https://github.com/rafritts/nori/blob/master/demos/hitl_demo.py) for a complete working example including an auto-responder that simulates the human side.

---

## Self-modification

Agents can be granted the ability to modify themselves at runtime. This is opt-in and additive — each tier includes everything below it.

| Tier | Constant | What it unlocks |
|---|---|---|
| 1 | `SelfModify.CUSTODIAN` | Update its own system prompt |
| 2 | `SelfModify.MODIFY` | Add or remove tools at runtime |
| 3 | `SelfModify.MUTATION` | Switch models, adjust `max_turns` |

```python
from nori import Agent, SelfModify

agent = Agent(
    name="AdaptiveAgent",
    system_prompt="You are a generic assistant.",
    self_modify=SelfModify.CUSTODIAN,
)

result = await agent.run(
    "Update your system prompt to say you are a Python coding assistant, "
    "then confirm your new role."
)
```

The self-modification capabilities are exposed as regular tools — the model decides when and why to invoke them.

See [`self_modify_demo.py`](https://github.com/rafritts/nori/blob/master/demos/self_modify_demo.py) for all three tiers in action.
