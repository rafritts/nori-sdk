# SPEC-11: Web & Browser Tool Suite

## Motivation

Web interaction for LLM agents requires different tools at different cost/capability levels. A single "browser tool" is the wrong abstraction — fetching a REST API, scraping a news site, and driving a multi-step login flow are fundamentally different problems. This spec defines a four-tool hierarchy that lets agents (and users) pick the right tool for the job.

---

## Tool Hierarchy

```
ApiClient    — raw HTTP, all methods/headers/auth. For APIs.
WebClient    — httpx GET + BeautifulSoup. For plain HTML sites.
BrowserClient — Playwright + BeautifulSoup. For JS-rendered sites.
BrowserAgent  — Playwright + LLM loop + targeted vision. For multi-step tasks.
```

Each level is strictly more capable and more expensive than the one above it. Agents should always use the cheapest tool that can do the job.

| Tool | JS hydration | LLM loop | Vision | Cost |
|---|---|---|---|---|
| `ApiClient` | no | no | no | cheapest |
| `WebClient` | no | no | no | cheap |
| `BrowserClient` | yes | no | no | moderate |
| `BrowserAgent` | yes | yes | on-demand | most expensive |

---

## ApiClient

Raw HTTP client. Does everything `httpx` can do: all methods, custom headers, auth, JSON/form bodies, arbitrary content types. Returns the raw response body and status code.

**Use when:** the target has a real API, or you need full control over the request.

```python
ApiClient(url="https://api.example.com/users", method="POST", body='{"name":"Ryan"}')
```

Previously named `WebClient`. Renamed to reflect its actual purpose.

---

## WebClient

`httpx` GET + BeautifulSoup. Fetches the raw HTML response and strips noise (scripts, styles, nav, footer, ads) to return clean readable text.

**Use when:** the target is a plain HTML site and the content is in the initial response. HN, Wikipedia, documentation, most blogs.

**Not for:** JS-rendered pages — content that only appears after JavaScript runs will be missing.

```python
WebClient(url="https://news.ycombinator.com")
# → clean text: story titles, scores, user names
```

---

## BrowserClient

Playwright loads the URL, waits for hydration (`networkidle`), then BeautifulSoup parses the fully-rendered HTML to return clean text.

**Use when:** the site requires JS to render its content, but the task is read-only (extract, don't interact). GitHub READMEs, React-rendered content, SPAs that populate on load.

**Not for:** multi-step tasks, form fills, login flows, anything requiring clicks.

```python
BrowserClient(url="https://github.com/anthropics/anthropic-sdk-python")
# → clean text: README, repo description, etc.
```

---

## BrowserAgent

Playwright + LLM decision loop + targeted element-scoped vision. Takes a natural-language task, navigates a browser autonomously, and returns the result.

**Use when:** the task requires interaction — clicking, typing, navigating between pages, logging in. Google Search, GitHub issues, any multi-step flow.

```python
BrowserAgent(task="Go to github.com/anthropics/anthropic-sdk-python, find the latest open issue, and return its title and first comment.")
```

### Architecture

`BrowserAgent` is a `@tool` that manages its own LLM message loop internally. It does not use a Nori `Agent` sub-instance.

**Why not a sub-Agent with primitive browser tools?**

The targeted screenshot feature requires injecting image content as `role=user` messages directly into the LLM conversation stream. The OpenAI API only supports images in user messages, not tool result messages — so a screenshot result cannot be returned from a `@tool` and seen as an image by the calling model. `BrowserAgent` manages its own message list and can inject vision content at the right point in the loop. This is a known constraint of the current `ToolResult` architecture; a future enhancement to `ToolResult` to support image content would enable the sub-Agent pattern.

### Loop

```
task prompt
    │
    ▼
Navigate + wait for hydration (networkidle, 8s timeout)
    │
    ▼
Extract interactive elements → compact JSON (with bounding boxes + stable IDs)
    │
    ▼
LLM receives: task + element JSON [+ prior action history]
    │
    ├─→ act: click / type / scroll / navigate / wait / done / fail
    │       │
    │       └─→ execute → hydrate if navigation → loop back to extract
    │
    └─→ screenshot(element_ids)   ← 1–4 element crops → 2×2 composite
            │
            └─→ LLM receives composite image → acts → no step count increment
```

---

## Element Extraction

### Tags captured

```
a, button, input, select, textarea,
[role="button"], [role="link"], [role="tab"], [role="menuitem"],
[onclick]
```

### Per-element fields

```json
{
  "id": "el_4",
  "tag": "button",
  "text": "Sign in",
  "type": "submit",
  "aria_label": "Sign in to your account",
  "bbox": { "x": 840, "y": 412, "w": 120, "h": 40 }
}
```

- `id` — stable within a loop iteration only; never carry IDs across steps
- `bbox` — used for mouse targeting and screenshot crops
- Null fields are omitted to keep the JSON compact

### Filtering

- **Hidden elements:** skip `display:none`, `visibility:hidden`, `opacity:0`, zero bounding box
- **Tracking links:** `href` checked against blocklist in `blocklist.py` (Google Analytics, Meta Pixel, Hotjar, etc.)
- **Duplicates:** same tag + text + href → keep first
- **Cap:** 60 elements per extraction, inputs first then buttons then links

---

## LLM Action Schema (BrowserAgent)

```json
{ "action": "navigate",        "url": "https://..." }
{ "action": "click",           "element_id": "el_N" }
{ "action": "type",            "element_id": "el_N", "text": "..." }
{ "action": "select",          "element_id": "el_N", "value": "..." }
{ "action": "scroll",          "direction": "down",  "px": 400 }
{ "action": "wait",            "ms": 1500 }
{ "action": "screenshot",      "element_ids": ["el_N", ...] }
{ "action": "screenshot_page" }
{ "action": "done",            "result": "..." }
{ "action": "fail",            "reason": "..." }
```

`screenshot` does not advance the step counter. `screenshot_page` is the full-viewport escape hatch — logged as a warning for token cost visibility.

---

## Targeted Screenshot Mechanics

### Color palette

| Slot | Color  | Hex       |
|------|--------|-----------|
| 1    | Red    | `#FF3B30` |
| 2    | Blue   | `#007AFF` |
| 3    | Green  | `#34C759` |
| 4    | Orange | `#FF9500` |

### Per-element crop

For each element in the request (max 4):
1. Get `bbox` from current element list
2. Expand by 60px padding, clip to viewport
3. `page.screenshot(clip=...)` → PNG
4. Draw colored border (4px) on the crop via Pillow — no DOM mutation
5. Scale to max 400px on longest dimension

### Composite

Grid layout stitched by `compositor.py`:
- 1 → 1×1, 2 → 1×2, 3–4 → 2×2 (empty cell for 3)
- Dark background, 6px gap between cells
- Plaintext legend returned alongside: `el_3=red, el_7=blue`

---

## BeautifulSoup Parsing (WebClient + BrowserClient)

After fetching HTML (via httpx or Playwright), shared parse logic in `nori/tools/browser/parser.py`:

1. Parse with `lxml` backend
2. Decompose: `script`, `style`, `nav`, `header`, `footer`, `aside`, `noscript`, `[class*="cookie"]`, `[class*="banner"]`
3. `get_text(separator="\n", strip=True)`
4. Collapse consecutive blank lines
5. Cap output at 8 000 characters (agents can request specific sections if more is needed)

---

## Dependencies

- `playwright` — Playwright Python async API
- `pillow` — image crop, resize, composite
- `beautifulsoup4` — HTML parsing for WebClient and BrowserClient
- `lxml` — fast BS4 backend

---

## File Layout

```
nori/tools/
    api_client.py            # ApiClient — raw HTTP (was WebClient)
    web_client.py            # WebClient — httpx + BS4
    web_agent.py             # WebAgent  — uses ApiClient (unchanged role)
    web_search.py            # WebSearch — uses WebClient (gets clean text now)
    browser/
        __init__.py          # exports BrowserClient, BrowserAgent
        client.py            # BrowserClient — Playwright + BS4
        tool.py              # BrowserAgent  — LLM loop (was BrowserUse)
        extractor.py         # element extraction + filtering
        screenshot.py        # per-element crop + highlight
        compositor.py        # 2×2 grid stitching
        parser.py            # shared BS4 parse logic
        blocklist.py         # tracking domain blocklist
        actions.py           # action execution
        prompts.py           # BrowserAgent system prompt
```

---

## Open Questions

- **Credentials in prompt:** passwords in the task string are plaintext in the conversation history. User's responsibility for now; could add a warning in a future pass.
- **2FA / CAPTCHA:** out of scope — `fail` gracefully with a clear message.
- **Shadow DOM:** `querySelectorAll` does not pierce shadow roots. Playwright supports it with `>>>` syntax; deferred to v2.
- **Multi-tab flows (OAuth):** out of scope for v1 — links that open new tabs should be handled via `navigate`.
- **ToolResult image support:** enabling the sub-Agent-with-primitive-tools pattern for `BrowserAgent` requires `ToolResult` to carry image content and `agent.py` to inject user messages for image tool results. Tracked as a future Agent enhancement.
