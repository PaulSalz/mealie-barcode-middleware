from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable


class ExecutorSaturated(RuntimeError):
    pass


class BoundedExecutor:
    """ThreadPoolExecutor with a hard cap on running + queued work.

    Python's ThreadPoolExecutor limits worker threads but its internal work queue
    is unbounded. A prolonged dependency outage can therefore turn a burst into
    unbounded retained callables/arguments. This wrapper adds admission control.
    """

    def __init__(self, *, max_workers: int, max_pending: int, thread_name_prefix: str):
        if max_workers < 1 or max_pending < 0:
            raise ValueError("invalid executor limits")
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=thread_name_prefix)
        self._slots = threading.BoundedSemaphore(max_workers + max_pending)

    def submit(
        self,
        fn: Callable[..., Any],
        /,
        *args: Any,
        block: bool = False,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Future:
        if block:
            acquired = self._slots.acquire(timeout=timeout) if timeout is not None else self._slots.acquire()
        else:
            acquired = self._slots.acquire(blocking=False)
        if not acquired:
            raise ExecutorSaturated("executor queue is full")
        try:
            future = self._executor.submit(fn, *args, **kwargs)
        except Exception:
            self._slots.release()
            raise
        future.add_done_callback(lambda _future: self._slots.release())
        return future

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)
