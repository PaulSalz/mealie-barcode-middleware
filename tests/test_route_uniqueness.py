from __future__ import annotations

from fastapi.routing import iter_route_contexts

from app.main import app


def _routes() -> list[tuple[str | None, str | None, tuple[str, ...], str]]:
    """Resolve concrete path operations through FastAPI's public route iterator."""
    rows = []
    for context in iter_route_contexts(app.routes):
        route = context.route
        endpoint = getattr(route, "endpoint", None)
        owner = ""
        if endpoint is not None:
            owner = f"{getattr(endpoint, '__module__', '')}.{getattr(endpoint, '__qualname__', getattr(endpoint, '__name__', ''))}"
        rows.append((
            type(route).__name__,
            context.path,
            tuple(sorted(getattr(route, "methods", None) or ())),
            owner,
        ))
    return rows


def _matching(path: str, method: str):
    method = method.upper()
    return [row for row in _routes() if row[1] == path and method in row[2]]


def test_scan_entry_points_are_registered_once() -> None:
    routes = _routes()
    assert len(_matching("/scan", "POST")) == 1, routes
    assert len(_matching("/scan/app", "POST")) == 1, routes
    received = _matching("/scanner/received", "POST")
    assert len(received) == 1, received


def test_barcode_detail_route_is_registered_once() -> None:
    routes = _routes()
    assert len(_matching("/barcodes/{barcode:path}", "GET")) == 1, routes
