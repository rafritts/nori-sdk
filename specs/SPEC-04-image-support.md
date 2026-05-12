# SPEC-04: Image Support

## Overview

Add first-class image support to Nori so agents can reason about images. Two distinct needs:

1. **Direct vision** — the model sees an image directly (initial user turn)
2. **Tool-based vision** — an agent views an image mid-task and gets a text description back (tool result)

These require different implementations because the OpenAI-compatible wire format only supports images in `user` role messages, not in `tool` result messages.

---

## Goals

- Allow `agent.run(prompt, images=[Image(...)])` to pass images into the initial user message
- Provide a `ViewImage` tool that agents can call mid-task to get a text description of an image
- Control token cost by auto-resizing images before encoding
- Be backward-compatible — callers that pass no images see no change

## Non-Goals

- Streaming image generation or output
- Image embedding/search
- Video frames
- Multi-turn image injection (images in follow-up user messages, not first turn)

---

## New Enum: `ResizeMode` (in `nori/enums.py`)

```python
class ResizeMode(IntEnum):
    NONE       = 0     # no resize
    AGGRESSIVE = 512   # logos, icons, small UI elements
    MODERATE   = 1024  # default — good for most photos and diagrams
    LIGHT      = 2048  # documents, charts where fine text matters
```

`ResizeMode` is an `IntEnum` — the values are the pixel dimensions themselves. This means callers can pass either a named constant or a raw integer interchangeably:

```python
Image("path.png", resize=ResizeMode.AGGRESSIVE)  # same as resize=512
Image("path.png", resize=768)                     # custom, works fine
```

No mapping logic needed — `resize > 0` means resize, value is the max dimension.

---

## New File: `nori/image.py`

### `Image` dataclass

```python
@dataclass
class Image:
    path: str | None = None                    # local filesystem path
    url:  str | None = None                    # remote URL (http/https) or data: URI
    data: bytes | None = None                  # raw image bytes

    detail: str = "auto"                       # "auto" | "low" | "high"
    resize: ResizeMode | int = ResizeMode.MODERATE
    output_format: str = "jpeg"                # "jpeg" | "png" — format after resize
    remove_from_context_after_read: bool = False
```

Exactly one of `path`, `url`, or `data` must be set. Constructor validates this.

**`Image.to_content_part() -> dict`**

Returns the OpenAI content-part dict:

```python
{"type": "image_url", "image_url": {"url": "<data URI>", "detail": "auto"}}
```

All sources are encoded to a base64 data URI client-side. Remote `https://` URLs are fetched and encoded rather than passed through — this works universally including local providers like Ollama that have no outbound internet access from the model server.

Logic:
1. If `url` is an `http(s)://` URL → fetch bytes, then encode
2. If `url` is already a `data:` URI → use directly
3. If `path` or `data` → load bytes, resize if needed, base64-encode, build data URI

**Resize logic (requires Pillow):**
```python
if self.resize > 0:
    w, h = img.size
    if max(w, h) > self.resize:
        scale = self.resize / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), PIL.Image.LANCZOS)
```

Always re-encode to `output_format` after resize (even if no resize occurred) to normalize and compress. JPEG at quality=85 is the default — dramatically smaller than PNG for photos.

**`Image.estimated_tokens() -> int`**

Returns a rough OpenAI token estimate:
- `detail="low"`: 85 tokens flat
- `detail="high"` or `"auto"`: `ceil(w/512) * ceil(h/512) * 170 + 85`
- Approximate and OpenAI-specific; other providers may differ

**Warning threshold:** Emit `logging.warning` if estimated tokens > 1000. Catches 4K screenshots before they silently eat context.

---

## Changes: `agent.run()`

```python
async def run(
    self,
    prompt: str,
    images: list[Image] | None = None,
    _trace_id: str | None = None,
    _parent_span_id: str | None = None,
) -> str:
```

If `images` is provided and non-empty, build the initial user message as a content array:

```python
content = [{"type": "text", "text": prompt}]
content += [img.to_content_part() for img in images]
self._history.append({"role": "user", "content": content})
```

If `images` is `None` or empty, keep the existing `{"role": "user", "content": prompt}` behavior. Fully backward-compatible.

---

## Changes: `_context_fill()`

Content can now be a list (array messages). Update to handle both:

```python
def _content_len(content) -> int:
    if isinstance(content, list):
        return sum(len(str(part)) for part in content)
    return len(str(content)) if content else 0

total = sum(_content_len(m.get("content")) for m in self._history)
```

Base64 image data in history inflates the character count, which is desirable — it correctly pressures the compaction threshold for image-heavy conversations.

---

## New Tool: `nori/tools/view_image.py`

### Why a separate tool?

Tool results (`{"role": "tool", "content": "..."}`) must be strings in the OpenAI wire format — images cannot be injected through tool results. So `ViewImage` makes a **second API call** to describe the image and returns the text description as the tool result.

This means `ViewImage`:
- Works for agents whose primary model is not multimodal
- Works mid-task, not just at the start
- Costs tokens for the description call, but the result is bounded text
- Loses information (it's a description, not the raw image)

### Interface

```python
class ViewImage:
    schema = {
        "type": "function",
        "function": {
            "name": "ViewImage",
            "description": "View an image and return a text description of its contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":   {"type": "string", "description": "Absolute path or https:// URL of the image."},
                    "prompt": {"type": "string", "description": "What specifically to look for or describe."},
                    "detail": {"type": "string", "enum": ["auto", "low", "high"], "default": "auto"},
                    "resize": {"type": "integer", "description": "Max pixel dimension for longest side before encoding. Use 512 (aggressive), 1024 (moderate), 2048 (light), or 0 (none). Default 1024.", "default": 1024},
                    "remove_from_context_after_read": {"type": "boolean", "description": "Strip this result from context after the current turn. Use when the image is not material to subsequent steps.", "default": False},
                    "reason": {"type": "string"},
                },
                "required": ["path", "prompt", "reason"],
            },
        },
    }

    async def __call__(self, path: str, prompt: str, reason: str, detail: str = "auto", resize: int = 1024, remove_from_context_after_read: bool = False) -> str:
        ...
```

### Implementation

`ViewImage` is a factory: `make_view_image(model: Model) -> ViewImage`, closing over the model config. The description sub-call is a single non-streaming completion. If the model isn't multimodal, the API will return a clear error.

---

## `remove_from_context_after_read` Stripping

**For `agent.run()` images:** After the first API call that includes the image, Nori scans history for content-array messages and replaces image parts marked `remove_from_context_after_read=True` with `{"type": "text", "text": "[image stripped]"}`. The text part of the message is preserved.

**For `ViewImage`:** The image bytes never enter the agent history (the sub-call is internal). When `remove_from_context_after_read=True`, Nori additionally strips the *text description* from the tool result after the turn, replacing it with `[image result stripped]`. The model read and used the information; it doesn't carry forward.

The model decides based on intent:
- Verifying a logo, reading a one-time value → `remove_from_context_after_read=True`
- Analyzing a diagram the rest of the task references → `False` (default)

---

## Changes: `nori/__init__.py`

```python
from nori.image import Image
from nori.enums import ..., ResizeMode

__all__ = [..., "Image", "ResizeMode"]
```

`ViewImage` lives in `nori/tools/view_image.py` and is not in `__init__.py`.

---

## New Dependency: Pillow

`uv add pillow`

Imported only inside `Image.to_content_part()`, not at module level. Callers that never use images won't hit an ImportError even if Pillow isn't installed.

---

## Token Cost Reference

| Image size | resize=NONE | resize=MODERATE (1024) | resize=AGGRESSIVE (512) |
|---|---|---|---|
| 512×512 | ~255 tokens | ~255 tokens | ~255 tokens |
| 1024×768 | ~595 tokens | ~595 tokens | ~255 tokens |
| 2048×1536 | ~2,295 tokens | ~595 tokens | ~255 tokens |
| 4000×3000 | ~8,585 tokens | ~765 tokens | ~255 tokens |

`detail="low"` is 85 tokens flat regardless of size — use it when structure matters more than content.

---

## Open Questions

1. **Multi-turn images**: No path to inject a new image mid-conversation outside of `ViewImage`. Out of scope for now.

2. **MIME type detection**: If the caller passes raw `data=` bytes with `output_format` unset, Nori needs to detect the type. Pillow's `Image.format` after `open()` covers this.

---

## Implementation Order

1. Add `ResizeMode(IntEnum)` to `nori/enums.py`
2. `nori/image.py` — `Image` dataclass with `to_content_part()` and `estimated_tokens()`
3. `nori/agent.py` — update `run()` signature, `_context_fill()`, and stripping logic
4. `nori/__init__.py` — export `Image`, `ResizeMode`
5. `nori/tools/view_image.py` — `make_view_image(model)` factory
6. `uv add pillow`
7. Unit tests for `Image` (resize, encoding, token estimate, validation)
8. Demo: `demos/vision_demo.py`
