from enum import Enum

from openai import AsyncOpenAI

from nori.context import inject_summary
from nori.exceptions import AntiSpinTerminated


class CheckpointScrutiny(Enum):
    STRICT = "strict"
    MODERATE = "moderate"
    LENIENT = "lenient"


_SCRUTINY_PROMPTS = {
    CheckpointScrutiny.STRICT: (
        "You are a strict progress evaluator. Any repetition, circular reasoning, "
        "or lack of forward progress is spin. Be conservative."
    ),
    CheckpointScrutiny.MODERATE: (
        "You are a balanced progress evaluator. Identify clear spin — repeated tool calls "
        "with no new information, or looping without progress."
    ),
    CheckpointScrutiny.LENIENT: (
        "You are a lenient progress evaluator. Only flag spin if the agent is clearly "
        "stuck with zero progress across many turns."
    ),
}


async def evaluate_checkpoint(
    recent_turns: list[dict],
    scrutiny: CheckpointScrutiny,
    client: AsyncOpenAI,
    model: str,
) -> tuple[bool, str]:
    """Returns (is_spinning, summary_of_recent_turns)."""
    turns_text = "\n".join(
        f"{m['role']}: {m.get('content', '')}" for m in recent_turns[-20:]
    )

    system = _SCRUTINY_PROMPTS[scrutiny]
    prompt = (
        f"Summarize what the agent has accomplished in the recent turns below, "
        f"then respond with exactly SPIN or PROGRESS on the last line.\n\n"
        f"Recent turns:\n{turns_text}"
    )

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    text = response.choices[0].message.content or ""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    verdict = lines[-1].upper() if lines else "PROGRESS"
    summary = "\n".join(lines[:-1]) if len(lines) > 1 else text

    return verdict == "SPIN", summary
