# Demos

Every demo is a complete, runnable Python file — imports, setup, and `asyncio.run(main())` included. Clone the repo and run any of them directly.

```bash
git clone https://github.com/rafritts/nori
cd nori
uv sync
python demos/easy_demo.py
```

Most demos require `NORI_CLI_PROVIDER` and `NORI_CLI_MODEL` (or equivalent) in your `.env`.

---

## Core

| Demo | What it shows |
|---|---|
| [`easy_demo.py`](https://github.com/rafritts/nori/blob/master/demos/easy_demo.py) | A basic multi-step bash agent. Good starting point. |
| [`medium1_demo.py`](https://github.com/rafritts/nori/blob/master/demos/medium1_demo.py) | A more involved task with multiple tools. |
| [`medium2_demo.py`](https://github.com/rafritts/nori/blob/master/demos/medium2_demo.py) | Multi-tool agent with file and shell work. |
| [`hard_demo.py`](https://github.com/rafritts/nori/blob/master/demos/hard_demo.py) | Broken repo recovery — agent finds and fixes bugs with no hints. |
| [`retail_demo.py`](https://github.com/rafritts/nori/blob/master/demos/retail_demo.py) | Realistic business workflow with structured data. |

## Tools

| Demo | What it shows |
|---|---|
| [`tool_decorator_demo.py`](https://github.com/rafritts/nori/blob/master/demos/tool_decorator_demo.py) | `@tool`, async tools, `summarize_output=False`, `.bind()`. |
| [`file_crud_demo.py`](https://github.com/rafritts/nori/blob/master/demos/file_crud_demo.py) | File read, write, edit, and search tools. |
| [`git_demo.py`](https://github.com/rafritts/nori/blob/master/demos/git_demo.py) | Git tool — status, diff, log, commit. |
| [`json_csv_demo.py`](https://github.com/rafritts/nori/blob/master/demos/json_csv_demo.py) | JsonRead and CsvRead tools. |
| [`vision_demo.py`](https://github.com/rafritts/nori/blob/master/demos/vision_demo.py) | ViewImage with a vision-capable model. |
| [`notify_demo.py`](https://github.com/rafritts/nori/blob/master/demos/notify_demo.py) | Notify tool with Slack and webhook. |

## Databases

| Demo | What it shows |
|---|---|
| [`postgres_demo/demo.py`](https://github.com/rafritts/nori/blob/master/demos/postgres_demo/demo.py) | Postgres tool against a real database. |
| [`redis_demo/demo.py`](https://github.com/rafritts/nori/blob/master/demos/redis_demo/demo.py) | Redis tool for key-value operations. |
| [`mongo_demo/demo.py`](https://github.com/rafritts/nori/blob/master/demos/mongo_demo/demo.py) | MongoDB tool against a real collection. |

## Browser

| Demo | What it shows |
|---|---|
| [`browser1_demo.py`](https://github.com/rafritts/nori/blob/master/demos/browser1_demo.py) | Basic web scraping with BrowserClient. |
| [`browser2_demo.py`](https://github.com/rafritts/nori/blob/master/demos/browser2_demo.py) | Multi-page navigation and extraction. |
| [`browser3_demo.py`](https://github.com/rafritts/nori/blob/master/demos/browser3_demo.py) | BrowserAgent for long-running browser tasks. |

## Patterns

| Demo | What it shows |
|---|---|
| [`agent_as_tool_demo.py`](https://github.com/rafritts/nori/blob/master/demos/agent_as_tool_demo.py) | Orchestrator delegating to specialist sub-agents. |
| [`parallel_demo.py`](https://github.com/rafritts/nori/blob/master/demos/parallel_demo.py) | Three specialist reviewers dispatched in parallel by an orchestrator. |
| [`hitl_demo.py`](https://github.com/rafritts/nori/blob/master/demos/hitl_demo.py) | HumanInput — agent pauses and waits for approval. |
| [`self_modify_demo.py`](https://github.com/rafritts/nori/blob/master/demos/self_modify_demo.py) | All three self-modification tiers: custodian, modify, mutation. |
| [`context_demo.py`](https://github.com/rafritts/nori/blob/master/demos/context_demo.py) | Running context summaries and autocompaction. |

## Configuration & Observability

| Demo | What it shows |
|---|---|
| [`config_override_demo.py`](https://github.com/rafritts/nori/blob/master/demos/config_override_demo.py) | Global config with per-agent overrides. |
| [`permissions_demo.py`](https://github.com/rafritts/nori/blob/master/demos/permissions_demo.py) | No restrictions, allow list, and deny list. |
| [`anti_spin_demo.py`](https://github.com/rafritts/nori/blob/master/demos/anti_spin_demo.py) | Healthy agent vs. spinning agent — anti-spin in action. |
| [`narration_demo.py`](https://github.com/rafritts/nori/blob/master/demos/narration_demo.py) | Default narration, custom callback, multi-agent prefixes. |
| [`observability_demo.py`](https://github.com/rafritts/nori/blob/master/demos/observability_demo.py) | Standard Python logging vs. structured audit stream with B3 tracing. |
