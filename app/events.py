"""Simple in-process event bus for Server-Sent Events (SSE)."""

import asyncio
import json
from typing import Any


class EventBus:
    """Fan-out pub/sub for SSE clients with bounded per-client buffers."""

    def __init__(self, max_queue_size: int = 64):
        self._subscribers: list[asyncio.Queue] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._max_queue_size = max(1, int(max_queue_size))

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue_size)
        self._subscribers.append(q)
        self._loop = asyncio.get_running_loop()
        return q

    def unsubscribe(self, q: asyncio.Queue):
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    @staticmethod
    def _put_latest(q: asyncio.Queue, msg: str) -> None:
        if q.full():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            # A consumer raced us between full()/get()/put(). Dropping one live
            # UI event is preferable to retaining unbounded memory.
            pass

    def _dispatch(self, msg: str):
        for q in list(self._subscribers):
            self._put_latest(q, msg)

    def publish(self, event: str, data: dict[str, Any]):
        msg = f"event: {event}\ndata: {json.dumps(data)}\n\n"
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._dispatch, msg)
        else:
            self._dispatch(msg)

    def publish_threadsafe(self, event: str, data: dict[str, Any]):
        msg = f"event: {event}\ndata: {json.dumps(data)}\n\n"
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._dispatch, msg)
        else:
            self._dispatch(msg)


scan_events = EventBus(max_queue_size=64)
