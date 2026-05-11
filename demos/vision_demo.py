"""
Vision demo: agent that uses ViewImage to inspect an image mid-task.

Creates a small test PNG at /tmp/nori_vision_demo.png, then asks an agent
to describe it using the ViewImage tool. Requires a multimodal model.
"""

import config
import asyncio

from nori import Agent
from nori.audit import AuditLogger
from nori.tools.view_image import make_view_image


IMAGE_PATH = "/tmp/nori_vision_demo.png"

SYSTEM_PROMPT = """\
You are a helpful assistant. When asked about an image, use the ViewImage tool to inspect it.
"""

TASK = f"""\
There is an image at {IMAGE_PATH}.

1. Use ViewImage to describe what you see in the image. The image is ephemeral — \
you won't need it after you've read it.
2. Based on the description, tell me the dominant color and approximate dimensions.
"""


def create_test_image() -> None:
    from PIL import Image as PILImage, ImageDraw
    img = PILImage.new("RGB", (400, 300), color=(70, 130, 180))  # steel blue background
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 50, 150, 150], fill=(255, 69, 0))   # orange-red square
    draw.ellipse([200, 75, 350, 225], fill=(50, 205, 50))   # lime green circle
    img.save(IMAGE_PATH)
    print(f"Test image created: {IMAGE_PATH} (400x300, steel blue bg, red square, green circle)")


async def main() -> None:
    create_test_image()

    view_image = make_view_image(config.MAIN_MODEL)

    agent = Agent(
        name="VisionAgent",
        system_prompt=SYSTEM_PROMPT,
        tools=[view_image],
        max_turns=10,
    )
    agent.narration = True
    agent.auditor = AuditLogger("logs/vision_demo.audit.log")

    print("=" * 60)
    print("Nori vision demo — ViewImage tool")
    print("=" * 60)
    print()

    result = await agent.run(TASK)

    print()
    print("=" * 60)
    print("Final response:")
    print("=" * 60)
    print(result)
    print()
    print(f"Turns: {agent.turn_count}  |  Tool calls: {len(agent.tool_calls)}  |  Cost: ${agent.cost:.4f}")


asyncio.run(main())
