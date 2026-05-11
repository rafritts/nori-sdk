from nori.enums import ResizeMode
from nori.model import Model


def make_view_image(model: Model):
    """Return a ViewImage tool bound to `model` for the description sub-call."""
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=model.api_key, base_url=model.base_url)

    class ViewImage:
        schema = {
            "type": "function",
            "function": {
                "name": "ViewImage",
                "description": (
                    "View an image and return a text description of its contents. "
                    "path may be a local file path or an https:// URL."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Absolute local file path or https:// URL of the image.",
                        },
                        "prompt": {
                            "type": "string",
                            "description": "What specifically to look for or describe in the image.",
                        },
                        "detail": {
                            "type": "string",
                            "enum": ["auto", "low", "high"],
                            "description": "Vision detail level. 'low' is cheapest (85 tokens flat). Default: auto.",
                        },
                        "resize": {
                            "type": "integer",
                            "description": (
                                "Max pixel dimension for the longest side before encoding. "
                                f"Presets: AGGRESSIVE={ResizeMode.AGGRESSIVE}, "
                                f"MODERATE={ResizeMode.MODERATE} (default), "
                                f"LIGHT={ResizeMode.LIGHT}, "
                                f"NONE={ResizeMode.NONE}. "
                                "Any integer is accepted."
                            ),
                        },
                        "remove_from_context_after_read": {
                            "type": "boolean",
                            "description": (
                                "Strip this result from context after the current turn. "
                                "Use when the image is not material to subsequent steps."
                            ),
                        },
                        "reason": {
                            "type": "string",
                            "description": "Your reason for calling this tool.",
                        },
                        "summary": {
                            "type": "string",
                            "description": "One-line description of what the image contains, shown in narration logs.",
                        },
                    },
                    "required": ["path", "prompt", "reason", "summary"],
                },
            },
        }

        summarize_output = False

        async def __call__(
            self,
            path: str,
            prompt: str,
            reason: str = "",
            detail: str = "auto",
            resize: int = ResizeMode.MODERATE,
            remove_from_context_after_read: bool = False,
        ) -> "ToolResult":
            from nori.image import Image
            from nori.tools.base import ToolResult
            from nori.tools._sandbox import sandbox_dir, check_path

            kwargs = {"detail": detail, "resize": resize}
            if path.startswith("http://") or path.startswith("https://"):
                img = Image(url=path, **kwargs)
            else:
                allowed = sandbox_dir.get()
                if allowed:
                    error = check_path(path, allowed)
                    if error:
                        return ToolResult(result=f"[error]\n{error}")
                img = Image(path=path, **kwargs)

            content = [
                {"type": "text", "text": prompt},
                img.to_content_part(),
            ]
            response = await client.chat.completions.create(
                model=model.id,
                messages=[{"role": "user", "content": content}],
            )
            result = response.choices[0].message.content or ""
            return ToolResult(result=result)

    return ViewImage()
