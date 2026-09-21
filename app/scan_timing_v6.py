from __future__ import annotations

import logging
import time

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


class ScanTimingMiddleware:
    """Measure scanner request latency without buffering the response."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") not in {"/scan", "/scan/app"}:
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                elapsed_ms = (time.perf_counter() - started) * 1000
                headers = MutableHeaders(scope=message)
                headers["Server-Timing"] = f"b2m-scan;dur={elapsed_ms:.1f}"
                headers["X-B2M-Scan-Ms"] = str(int(round(elapsed_ms)))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            if elapsed_ms >= 1000:
                logger.warning(
                    "Slow scan request: %s took %.0f ms%s",
                    scope.get("path"),
                    elapsed_ms,
                    "" if response_started else " before response start",
                )
