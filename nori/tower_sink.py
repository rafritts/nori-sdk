"""
Process-level singleton WebSocket sink for nori-tower.

One WS connection per process — all agents share it.
Configure via nori.configure(control_tower="http://localhost:7740", project="my-project").
"""
import asyncio
import json
from datetime import datetime, timezone

_url: str | None = None
_project: str = "default"
_queue: asyncio.Queue = asyncio.Queue()
_ws = None
_drain_task: asyncio.Task | None = None


def configure(url: str, project: str = "default") -> None:
    global _url, _project
    # Normalize to ws:// scheme
    url = url.rstrip("/")
    if url.startswith("https://"):
        url = "wss://" + url[8:]
    elif url.startswith("http://"):
        url = "ws://" + url[7:]
    if not url.endswith("/ws"):
        url += "/ws"
    _url = url
    _project = project


def emit(event: str, **fields) -> None:
    if _url is None:
        return
    payload = {
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": event,
        "project": _project,
        **fields,
    }
    try:
        _queue.put_nowait(payload)
    except asyncio.QueueFull:
        pass
    _ensure_drain()


def _ensure_drain() -> None:
    global _drain_task
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _drain_task is None or _drain_task.done():
        _drain_task = loop.create_task(_drain())


async def _drain() -> None:
    global _ws
    try:
        import websockets
    except ImportError:
        return

    while True:
        try:
            payload = await asyncio.wait_for(_queue.get(), timeout=30)
        except asyncio.TimeoutError:
            # Keep alive — ping the server if connected
            if _ws is not None:
                try:
                    await _ws.ping()
                except Exception:
                    _ws = None
            continue

        if _url is None:
            continue

        for attempt in range(2):
            try:
                if _ws is None or _ws.closed:
                    _ws = await websockets.connect(_url)
                    await _ws.send(json.dumps({"type": "hello", "project": _project}))
                await _ws.send(json.dumps({"type": "event", "payload": payload}))
                break
            except Exception:
                _ws = None
                if attempt == 0:
                    await asyncio.sleep(0.5)
