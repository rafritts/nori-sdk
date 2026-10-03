import os
from dataclasses import dataclass

from typesafe_sdk import AsyncTypeSafeClient, Noul

from nori.enums import CheckpointScrutiny

# Pinned. Scrutiny thresholds below were chosen for this version's probabilities.
# jev-latest can move, and a new version would need the cutoffs checked again.
JEV_MODEL = "jev-1.13.0"
# https://docs.typesafe.ai/models — input only; output tokens are free.
JEV_USD_PER_MILLION_INPUT = 0.042

# Last N non-marker messages sent as state. Each content field is clipped so a
# long tool result cannot crowd out the rest of the window (32k token budget
# for state plus the question).
_MAX_TURNS = 20
_CONTENT_LIMIT = 1500
_ARGS_LIMIT = 400

# One question for every scrutiny level. Scrutiny is the probability at which
# we stop, which is the part that belongs in code.
_SPIN = Noul(
    instructions=(
        "Is the agent spinning in `recent_turns`, given `task`? "
        "Spinning means those turns repeat work or do not move the task forward."
    ),
    criteria={
        "true": (
            "The same action or idea is repeating, and the new turns do not "
            "contain new information that moves the task forward."
        ),
        "false": (
            "The recent turns advance the task. A retry that tries a different "
            "approach, or that uses new information from the last result, is progress."
        ),
    },
)

# Stop when P(spin) is at least this. 0.5 is a coin flip; strict treats that
# as enough to stop. Lenient waits for a strong yes.
THRESHOLDS = {
    CheckpointScrutiny.STRICT: 0.50,
    CheckpointScrutiny.MODERATE: 0.75,
    CheckpointScrutiny.LENIENT: 0.90,
}


@dataclass
class Checkpoint:
    every: int
    scrutiny: CheckpointScrutiny = CheckpointScrutiny.MODERATE
    compact: bool = False

    def __post_init__(self):
        if self.every <= 0:
            raise ValueError("Checkpoint.every must be a positive integer.")


@dataclass(frozen=True)
class CheckpointVerdict:
    spinning: bool
    noul: float
    threshold: float
    input_tokens: int
    note: str

    @property
    def cost_usd(self) -> float:
        return self.input_tokens * JEV_USD_PER_MILLION_INPUT / 1_000_000


def _plain_text(content: object, limit: int) -> str:
    """Text Jev can read. Image payloads are replaced; nothing else is sent."""
    if content is None:
        return ""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        bits: list[str] = []
        for part in content:
            if isinstance(part, str):
                bits.append(part)
            elif isinstance(part, dict):
                if part.get("type") == "text":
                    bits.append(str(part.get("text") or ""))
                elif part.get("type") == "image_url" or "image_url" in part:
                    bits.append("[image]")
        text = "\n".join(bit for bit in bits if bit)
    else:
        text = str(content)
    text = text.strip()
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def _tool_calls(message: dict) -> list[dict]:
    calls = []
    for tc in message.get("tool_calls") or []:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") or {}
        if not isinstance(fn, dict):
            continue
        name = str(fn.get("name") or "")
        if not name:
            continue
        call: dict = {"name": name}
        args = fn.get("arguments")
        if isinstance(args, str) and args.strip():
            call["arguments"] = _plain_text(args, _ARGS_LIMIT)
        tid = tc.get("id")
        if isinstance(tid, str):
            call["id"] = tid
        calls.append(call)
    return calls


def checkpoint_state(turns: list[dict], task: str) -> dict:
    """State for the spinning question. Marker messages and image bytes are left out."""
    names: dict[str, str] = {}
    recent: list[dict] = []
    for message in turns:
        if not isinstance(message, dict) or message.get("_marker"):
            continue
        role = message.get("role")
        if role not in {"user", "assistant", "tool"}:
            continue
        item: dict = {"role": role}
        text = _plain_text(message.get("content"), _CONTENT_LIMIT)
        if text:
            item["content"] = text
        if role == "assistant":
            calls = _tool_calls(message)
            if calls:
                item["tool_calls"] = [{k: v for k, v in call.items() if k != "id"} for call in calls]
                for call in calls:
                    if "id" in call:
                        names[call["id"]] = call["name"]
        if role == "tool":
            tid = message.get("tool_call_id")
            if isinstance(tid, str) and tid in names:
                item["name"] = names[tid]
        if len(item) > 1:
            recent.append(item)
    return {
        "task": _plain_text(task, _CONTENT_LIMIT) or "(not recorded)",
        "recent_turns": recent[-_MAX_TURNS:],
    }


def task_from_history(history: list[dict]) -> str:
    """The first real user message. Checkpoint notes are not the task."""
    for message in history:
        if isinstance(message, dict) and message.get("role") == "user" and not message.get("_marker"):
            return _plain_text(message.get("content"), _CONTENT_LIMIT)
    return ""


def _trace(turns: list[dict]) -> str:
    parts = []
    for turn in turns[-8:]:
        role = turn.get("role", "")
        if role == "assistant" and turn.get("tool_calls"):
            names = ", ".join(call["name"] for call in turn["tool_calls"])
            parts.append(f"assistant called {names}")
        elif role == "tool":
            name = turn.get("name") or "tool"
            snippet = (turn.get("content") or "")[:80]
            parts.append(f"{name}: {snippet}" if snippet else name)
        else:
            snippet = (turn.get("content") or "")[:80]
            parts.append(f"{role}: {snippet}" if snippet else role)
    return " | ".join(parts) if parts else "(no turns)"


def _require_api_key() -> str:
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "Anti-spin checkpoints use Jev (TypeSafe), but TYPESAFE_API_KEY is not set.\n\n"
            "To fix this, do one of:\n"
            "  1. Export it in your shell: export TYPESAFE_API_KEY=your-key-here\n"
            "  2. Add it to a .env file in your project root: TYPESAFE_API_KEY=your-key-here"
        )
    return key


async def _judge(state: dict) -> tuple[float, int]:
    """Return (P(spin), input_tokens) from Jev."""
    key = _require_api_key()
    async with AsyncTypeSafeClient(api_key=key, model=JEV_MODEL) as client:
        response = await client.system_one(state=state, questions={"spinning": _SPIN})
    tokens = 0
    if response.usage is not None and response.usage.input_tokens:
        tokens = response.usage.input_tokens
    return response.nouls["spinning"].noul, tokens


async def evaluate_checkpoint(
    recent_turns: list[dict],
    scrutiny: CheckpointScrutiny,
    task: str = "",
) -> CheckpointVerdict:
    """Return whether the recent turns are spinning, and the probability Jev gave.

    A Jev error propagates. The run stops on a failed check; it is not treated
    as progress and it is not treated as spin.
    """
    threshold = THRESHOLDS[scrutiny]
    state = checkpoint_state(recent_turns, task)
    if not state["recent_turns"]:
        return CheckpointVerdict(
            spinning=False,
            noul=0.0,
            threshold=threshold,
            input_tokens=0,
            note="No recent turns to judge.",
        )
    noul, input_tokens = await _judge(state)
    spinning = noul >= threshold
    relation = ">=" if spinning else "<"
    note = (
        f"P(spin)={noul:.2f} {relation} {threshold:.2f} ({scrutiny.value}). "
        f"Recent: {_trace(state['recent_turns'])}"
    )
    return CheckpointVerdict(
        spinning=spinning,
        noul=noul,
        threshold=threshold,
        input_tokens=input_tokens,
        note=note,
    )
