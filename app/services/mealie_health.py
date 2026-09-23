from __future__ import annotations

import threading
import time

import httpx

from app.services import mealie_http

_lock = threading.Lock()
_cache: tuple[float, bool] | None = None
_DEFAULT_TTL_SECONDS = 15.0


def mealie_reachable(*, ttl_seconds: float = _DEFAULT_TTL_SECONDS, force: bool = False) -> bool:
    """Return Mealie reachability with a process-wide short TTL cache.

    Health polling is performed by Docker, the dashboard and the browser. Sharing
    one cached probe prevents all of those callers from independently hitting
    Mealie every few seconds. `force=True` is reserved for explicit user tests.
    """
    global _cache
    now = time.monotonic()
    if not force:
        with _lock:
            cached = _cache
            if cached and now - cached[0] < max(0.0, ttl_seconds):
                return cached[1]

    try:
        response = mealie_http.get(
            "/api/app/about",
            timeout=5,
            log_name="health probe",
        )
        reachable = response.status_code == 200
    except httpx.HTTPError:
        reachable = False

    with _lock:
        _cache = (time.monotonic(), reachable)
    return reachable


def clear_mealie_health_cache() -> None:
    global _cache
    with _lock:
        _cache = None
