from __future__ import annotations

import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# httpx.Client is thread-safe for concurrent request use. One process-wide pool
# avoids reconnecting/TLS/TCP setup across scanner, sync and UI worker threads.
_client = httpx.Client(
    limits=httpx.Limits(
        max_connections=24,
        max_keepalive_connections=12,
        keepalive_expiry=60.0,
    ),
)


def headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.mealie_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def request(
    method: str,
    path: str,
    *,
    timeout: float | httpx.Timeout = 10.0,
    params: dict | None = None,
    json=None,
    log_name: str | None = None,
) -> httpx.Response:
    url = f"{settings.mealie_url.rstrip('/')}/{path.lstrip('/')}"
    started = time.monotonic()
    response = _client.request(
        method,
        url,
        headers=headers(),
        params=params,
        json=json,
        timeout=timeout,
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    if elapsed_ms >= 1000:
        logger.warning("Slow Mealie request: %s took %d ms", log_name or path, elapsed_ms)
    return response


def get(path: str, **kwargs) -> httpx.Response:
    return request("GET", path, **kwargs)


def post(path: str, **kwargs) -> httpx.Response:
    return request("POST", path, **kwargs)


def put(path: str, **kwargs) -> httpx.Response:
    return request("PUT", path, **kwargs)


def delete(path: str, **kwargs) -> httpx.Response:
    return request("DELETE", path, **kwargs)
