# SPEC-11: Browser Tool

## Motivation

Existing browser automation tools for LLMs are token-expensive and often unreliable. The core problem: they either dump full-page screenshots at every step (expensive vision tokens) or send raw HTML (megabytes of noise). Both approaches give the model too much irrelevant data and too little actionable structure.

This spec describes a browser tool that inverts the default: **structured element extraction first, targeted vision on demand**. The LLM sees a compact JSON list of interactive elements and asks for a cropped, element-scoped screenshot only when it genuinely needs visual context. Full-page screenshots are an explicit escape hatch, not the default.

---

## Architecture Overview

`BrowserUse(task)` is a single high-level tool. Internally it runs a Playwright-backed agent loop:

```
task prompt
    │
    ▼
Navigate + wait for hydration
    │
    ▼
Extract interactive elements → compact JSON (with bounding boxes + stable IDs)
    │
    ▼
LLM receives: task + element JSON [+ prior action history]
    │
    ├─→ act: click / type / scroll / navigate / done / fail
    │       │
    │       └─→ execute → loop back to extract
    │
    └─→ screenshot(element_id)   ← targeted crop, highlighted
            │
            └─→ LLM receives element crop → acts → loop back to extract
```

The loop terminates when the LLM emits `done(result)` or `fail(reason)`, or when a step limit is reached.

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
  "href": null,
  "placeholder": null,
  "aria_label": "Sign in to your account",
  "name": null,
  "bbox": { "x": 840, "y": 412, "w": 120, "h": 40 }
}
```

- `id` — stable within a loop iteration, used by the LLM to reference elements in actions
- `bbox` — always included; used for targeted screenshots and scroll-into-view
- Fields that don't apply to a tag are `null` and omitted from the JSON output to save tokens

### Filtering

**Hidden elements:** skip if `display: none`, `visibility: hidden`, `opacity: 0`, or bounding box is zero-dimension.

**Tracking/analytics links:** for `<a>` tags, check `href` against a blocklist of known tracking domains and patterns (Google Analytics, Facebook Pixel, Hotjar, Segment, Mixpanel, Twitter/X pixel, etc.). The blocklist lives in `nori/tools/browser/blocklist.py` as a frozenset of domain fragments.

**Duplicate suppression:** if multiple elements have identical text + tag + href, keep the first occurrence.

**Cap:** maximum 60 elements per extraction. If more exist, prioritize: inputs first, then buttons, then links in DOM order.

---

## LLM Action Schema

The internal LLM responds with a single JSON action per turn. The tool parses and executes it.

```json
{ "action": "click",       "element_id": "el_3" }
{ "action": "type",        "element_id": "el_7", "text": "myusername" }
{ "action": "select",      "element_id": "el_2", "value": "United States" }
{ "action": "scroll",      "direction": "down",  "px": 400 }
{ "action": "navigate",    "url": "https://example.com/page" }
{ "action": "screenshot",  "element_ids": ["el_3", "el_7"] }
{ "action": "screenshot_page" }
{ "action": "wait",        "ms": 1500 }
{ "action": "done",        "result": "Notifications: ..." }
{ "action": "fail",        "reason": "Could not locate login form after 3 attempts" }
```

- `screenshot(element_ids)` — targeted crops of 1–4 elements, stitched into a single composite image (see below). Does not advance the loop; the LLM receives the composite and must then emit an action.
- `screenshot_page` — full viewport screenshot. Explicit escape hatch for when the element list is semantically useless (e.g., all `div.sc-abc123` with no readable labels) and layout context is the only way forward. Logged as a warning (token cost signal).
- `wait` — for pages that hydrate slowly after a click (e.g., SPA route transitions).

### System prompt for the internal LLM

The system prompt instructs the model to:
- Prefer acting on the element list without requesting a screenshot
- Request `screenshot(element_ids)` when specific elements are ambiguous — up to 4 at once; batch related elements into one request rather than asking sequentially
- Use `screenshot_page` only when the entire element list is unreadable noise (no semantic labels anywhere) and spatial layout is the only remaining signal
- Element IDs are valid only for the current extraction — never reference an ID from a prior step
- Emit `done` as soon as the original task is complete — don't explore beyond what was asked
- Emit `fail` rather than looping indefinitely if the task cannot be completed

---

## Targeted Screenshot Mechanics

### Crop palette

Four fixed highlight colors, assigned in request order:

| Slot | Color   | Hex       |
|------|---------|-----------|
| 1    | Red     | `#FF3B30` |
| 2    | Blue    | `#007AFF` |
| 3    | Green   | `#34C759` |
| 4    | Orange  | `#FF9500` |

### Per-element crop

For each requested `element_id`:

1. Look up `bbox` in the current element list
2. Inject CSS: `outline: 3px solid <color>; outline-offset: 2px` on the element
3. Compute crop region: `bbox` expanded by **60px padding** on all sides, clipped to viewport bounds
4. Capture via `page.screenshot(clip=crop_region, type="png")`
5. Remove the injected CSS
6. Scale the crop so its longest dimension is at most **400px** (preserves readability, controls token cost)

### Composite image

Crops are stitched into a single image using a **grid layout**:

- 1 element → 1×1 (single image, no grid overhead)
- 2 elements → 1×2 (side by side)
- 3 elements → 2×2 with bottom-right cell empty
- 4 elements → 2×2

Each cell is padded to a uniform size (the largest crop's dimensions) with a neutral background. A thin label strip below each cell shows `el_N` in the matching highlight color.

The composite is returned as a single base64 PNG. The tool also returns a plaintext legend alongside the image:

```
el_3 = red    | Sign in button (bottom of form)
el_7 = blue   | Username input
el_12 = green | "Notifications" div — text visible but class is sc-xr99t2
```

The LLM receives both and can reason about all four elements in one vision pass.

### Full page screenshot

`screenshot_page` captures the current viewport only (not the full scrollable page). Resize to max 1280px wide. This is still expensive but bounded.

---

## Hydration Waiting

After every navigation or click that triggers a page transition:

1. `page.wait_for_load_state("domcontentloaded")`
2. `page.wait_for_load_state("networkidle", timeout=8000)` — catches SPA hydration; timeout is generous but capped
3. If `networkidle` times out, proceed anyway — the page is probably usable

After a `type` or `select` action, no wait (assume the page doesn't reload).
After a `click` on a non-navigation button (e.g., form submit), use `networkidle` with a shorter timeout (3000ms), then proceed.

---

## Session and State

Each `BrowserUse` call gets a fresh Playwright `BrowserContext` — isolated cookies, storage, and cache. This is safe by default: no cross-task credential leakage.

Within a single call, state persists across the loop: cookies set during login are available for subsequent navigation steps.

**Browser lifecycle:** a single Playwright `Browser` instance is shared within an agent run (lazy-initialized, closed on agent teardown). Creating a new browser per tool call is too slow (~1s overhead).

---

## Configuration

```python
BrowserUse(
    task="Log into example.com and return my notification count.",
    headless=True,          # default True; False for debugging
    max_steps=20,           # loop step limit; default 20
    viewport=(1280, 800),   # default
    timeout_ms=30_000,      # per-action timeout
)
```

`headless`, `viewport`, and `timeout_ms` can also be set via `Config.browser` defaults (follows the existing config pattern from SPEC-05).

---

## Dependencies

- `playwright` (Python) — async API, Chromium backend
- `Pillow` — for image resizing before base64 encoding

Installation note: `playwright install chromium` must be run after `uv add playwright`. This is a one-time setup step. The tool raises a clear `RuntimeError` with instructions if Playwright binaries are not found.

---

## File Layout

```
nori/tools/browser/
    __init__.py          # exports BrowserUse
    tool.py              # @tool BrowserUse — entry point, loop driver
    extractor.py         # element extraction + filtering logic
    screenshot.py        # per-element crop + resize + highlight
    compositor.py        # stitch 1–4 crops into 2x2 grid + legend
    blocklist.py         # tracking/analytics domain blocklist
    actions.py           # action execution (click, type, scroll, etc.)
    prompts.py           # system prompt for internal LLM
```

`BrowserUse` is added to `nori/tools/__init__.py` and available as a first-class tool.

---

## Implementation Plan

1. **Dependencies** — `uv add playwright pillow`; add `playwright install chromium` to setup docs
2. **`blocklist.py`** — curate tracking domain list from public sources (uBlock Origin, EasyPrivacy)
3. **`extractor.py`** — Playwright `page.query_selector_all`, attribute extraction, filtering, ID assignment
4. **`screenshot.py`** — bounding box lookup, CSS highlight, crop + pad, resize, base64 encode
5. **`actions.py`** — action dispatch: click, type, select, scroll, navigate, wait
6. **`prompts.py`** — system prompt for internal decision LLM
7. **`tool.py`** — loop: navigate → extract → LLM → action → repeat; step limit; done/fail handling
8. **Browser lifecycle** — lazy init, context-per-call, shared browser instance
9. **Config** — `Config.browser` defaults for headless, viewport, timeout
10. **Tests** — unit tests for extractor (mock DOM), screenshot (mock bbox), blocklist; integration test with a local HTML fixture served via `http.server`
11. **Demo** — `demos/browser_demo.py` showing a real multi-step task

---

## Open Questions

- **Credentials in prompt:** the task prompt may contain passwords in plaintext. Should the tool warn when it detects credential-shaped content in the task string? Or is that the user's responsibility?
- **2FA / CAPTCHA:** both are currently out of scope. The tool should `fail` gracefully with a clear message rather than hanging.
- **PDF / file downloads:** out of scope for v1. If a click triggers a download, the tool should detect it and surface the file path.
- **Multi-tab navigation:** some flows open links in new tabs (OAuth). Playwright supports this but adds complexity. Out of scope for v1 — links that open new tabs should be handled via `navigate` instead.
- **Element ID stability across steps:** IDs (`el_0`, `el_1`) are reassigned every extraction. The LLM cannot carry an `element_id` across loop iterations — it must always act on the IDs from the most recent extraction. The system prompt must make this explicit.
