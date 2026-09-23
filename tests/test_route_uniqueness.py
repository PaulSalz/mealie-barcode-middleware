from __future__ import annotations

from collections.abc import Iterable

from app.main import app


def _walk_routes(routes: Iterable, seen: set[int] | None = None):
    """Yield concrete routes across FastAPI/Starlette nested router wrappers."""
    seen = seen or set()
    for route in routes:
        marker = id(route)
        if marker in seen:
            continue
        seen.add(marker)
        yield route

        nested = getattr(route, "routes", None)
        if nested:
            yield from _walk_routes(nested, seen)
            continue

        router = getattr(route, "router", None)
        router_routes = getattr(router, "routes", None) if router is not None else None
        if router_routes:
            yield from _walk_routes(router_routes, seen)


def _routes() -> list[tuple[str | None, str | None, tuple[str, ...]]]:
    rows = []
    for route in _walk_routes(app.router.routes):
        rows.append((
            type(route).__name__,
            getattr(route, "path", None) or getattr(route, "path_format", None),
            tuple(sorted(getattr(route, "methods", None) or ())),
        ))
    return rows


def _count(path: str, method: str) -> int:
    method = method.upper()
    return sum(1 for _kind, route_path, methods in _routes() if route_path == path and method in methods)


def test_scan_entry_points_are_registered_once() -> None:
    routes = _routes()
    assert _count("/scan", "POST") == 1, routes
    assert _count("/scan/app", "POST") == 1, routes
    assert _count("/scanner/received", "POST") == 1, routes


def test_barcode_detail_route_is_registered_once() -> None:
    routes = _routes()
    assert _count("/barcodes/{barcode:path}", "GET") == 1, routes
