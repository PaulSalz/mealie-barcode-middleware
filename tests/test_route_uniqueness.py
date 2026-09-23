from app.main import app


def _routes() -> list[tuple[str | None, str | None, tuple[str, ...]]]:
    rows = []
    for route in app.router.routes:
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
