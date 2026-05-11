"""BrowserUse tool — drives a Playwright browser with an LLM decision loop."""

import json
import logging

from openai import AsyncOpenAI
from playwright.async_api import Page

import nori.config as config
from nori.tool import tool
from nori.tools.base import ToolResult
from nori.tools.browser.actions import execute_action
from nori.tools.browser.compositor import compose_grid
from nori.tools.browser.extractor import extract_elements
from nori.tools.browser.prompts import SYSTEM_PROMPT, build_state_message
from nori.tools.browser.screenshot import PALETTE, crop_element, full_page_screenshot

logger = logging.getLogger("nori.browser")

_MAX_STEPS = 20
_HYDRATION_TIMEOUT = 8_000
_SCREENSHOT_ACTIONS = {"screenshot", "screenshot_page"}
_HYDRATION_ACTIONS  = {"click", "navigate"}


async def _hydrate(page: Page) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=_HYDRATION_TIMEOUT)
    except Exception:
        pass  # proceed even if the page never goes fully idle


async def _get_screenshots(
    page: Page,
    element_ids: list[str],
    elements: list[dict],
) -> tuple[str, str] | None:
    el_map = {el["id"]: el for el in elements}
    crops, valid_ids, valid_colors = [], [], []

    for i, eid in enumerate(element_ids[:4]):
        el = el_map.get(eid)
        if el is None:
            logger.warning("screenshot requested for unknown element %s", eid)
            continue
        color_hex, color_name = PALETTE[i]
        try:
            crops.append(await crop_element(page, el["bbox"], color_hex))
            valid_ids.append(eid)
            valid_colors.append((color_hex, color_name))
        except Exception as exc:
            logger.warning("crop failed for %s: %s", eid, exc)

    if not crops:
        return None
    return compose_grid(crops, valid_ids, valid_colors)


async def _decide(
    client: AsyncOpenAI,
    model_id: str,
    messages: list[dict],
    task: str,
    page: Page,
    elements: list[dict],
    history: list[str],
) -> dict:
    """Append current state to messages, call LLM, handle screenshot sub-requests, return action."""
    messages.append({
        "role": "user",
        "content": build_state_message(task, page.url, elements, history),
    })

    while True:
        response = await client.chat.completions.create(
            model=model_id,
            messages=messages,
            response_format={"type": "json_object"},
            max_tokens=512,
        )
        raw = response.choices[0].message.content or "{}"
        messages.append({"role": "assistant", "content": raw})

        try:
            action = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("LLM returned invalid JSON: %s", raw)
            return {"action": "fail", "reason": "internal: LLM returned invalid JSON"}

        action_name = action.get("action", "")

        if action_name == "screenshot":
            result = await _get_screenshots(page, action.get("element_ids", []), elements)
            if result:
                b64, legend = result
                messages.append({"role": "user", "content": [
                    {"type": "text", "text": f"{legend}\n\nPlease act based on what you see."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}},
                ]})
            else:
                messages.append({"role": "user", "content": "Screenshot failed. Please act on the element list."})

        elif action_name == "screenshot_page":
            logger.warning("full-page screenshot requested (high token cost)")
            b64 = await full_page_screenshot(page)
            messages.append({"role": "user", "content": [
                {"type": "text", "text": "Full page screenshot. Please act."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}},
            ]})

        else:
            return action


@tool
async def BrowserUse(task: str) -> ToolResult:
    """Navigate a web browser to complete a task. Handles JS-rendered pages, login flows, form fills, and multi-step interactions."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return ToolResult(result="playwright is not installed: run `uv add playwright && playwright install chromium`")

    _d = config.get_defaults()
    model = _d.tool_models.get(BrowserUse) or _d.model
    if model is None:
        return ToolResult(result="no model configured — call nori.configure(model=...) first")

    client = AsyncOpenAI(api_key=model.api_key, base_url=model.base_url)
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    history:  list[str]  = []
    steps = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page    = await context.new_page()

        try:
            while steps < _MAX_STEPS:
                elements = await extract_elements(page)
                action   = await _decide(client, model.id, messages, task, page, elements, history)

                action_name = action.get("action", "")
                logger.info("browser action %d/%d: %s", steps + 1, _MAX_STEPS, action_name)

                if action_name == "done":
                    return ToolResult(result=action.get("result", "Task completed."))

                if action_name == "fail":
                    return ToolResult(result=f"Task failed: {action.get('reason', 'unknown')}")

                error = await execute_action(page, action, elements)
                steps += 1

                if error:
                    history.append(f"{action_name}: error — {error}")
                    messages.append({"role": "user", "content": f"Action error: {error}"})
                else:
                    history.append(f"{action_name}: ok")
                    if action_name in _HYDRATION_ACTIONS:
                        await _hydrate(page)

        finally:
            await browser.close()

    return ToolResult(result=f"Step limit ({_MAX_STEPS}) reached without completing the task.")
