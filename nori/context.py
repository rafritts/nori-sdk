from dataclasses import dataclass
from pathlib import Path

from nori.enums import ContextRole


@dataclass
class ContextFile:
    path: str | Path
    role: ContextRole

    @property
    def content(self) -> str:
        return Path(self.path).read_text()


_SUMMARY_MARKER = "__running_summary__"


async def update_running_summary(
    history: list[dict],
    current_summary: str,
    completer,
    model: str,
) -> str:
    recent = [m for m in history if m.get("role") != "system" and m.get("_marker") != _SUMMARY_MARKER]
    if not recent:
        return current_summary

    turns_text = "\n".join(
        f"{m['role']}: {m.get('content', '')}" for m in recent[-10:]
    )
    prompt = (
        f"Update this running summary with what just happened.\n\n"
        f"Current summary:\n{current_summary}\n\n"
        f"Recent activity:\n{turns_text}"
    )
    result = await completer.complete(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return result.message.content or current_summary


def inject_summary(history: list[dict], summary: str) -> list[dict]:
    """Return history with the summary injected as the first user message."""
    filtered = [m for m in history if m.get("_marker") != _SUMMARY_MARKER]
    summary_msg = {"role": "user", "content": f"[Context so far]\n{summary}", "_marker": _SUMMARY_MARKER}
    return [summary_msg] + filtered
