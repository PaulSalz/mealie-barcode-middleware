from fastapi.routing import APIRoute

from app.main import app


def _count(path: str, method: str) -> int:
    method = method.upper()
    return sum(
        1
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path == path
        and method in (route.methods or set())
    )


def test_scan_entry_points_are_registered_once() -> None:
    assert _count("/scan", "POST") == 1
    assert _count("/scan/app", "POST") == 1
    assert _count("/scanner/received", "POST") == 1


def test_barcode_detail_route_is_registered_once() -> None:
    assert _count("/barcodes/{barcode:path}", "GET") == 1
