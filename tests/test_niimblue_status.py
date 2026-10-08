import httpx

from app.services import niimblue


def test_printer_status_reports_niimblue_connection_failure(monkeypatch):
    cfg = {
        "url": "http://niimblue-node:3010",
        "transport": "ble",
        "address": "AA:BB:CC:DD:EE:FF",
        "print_task": "D110M_V4",
        "dpi": 300,
        "max_label_width_mm": 50,
    }
    monkeypatch.setattr(niimblue, "config", lambda: cfg)
    monkeypatch.setattr(niimblue.time, "sleep", lambda _seconds: None)

    def fail_request(method, path, **_kwargs):
        request = httpx.Request(method, f"{cfg['url']}{path}")
        raise httpx.ConnectError("Connection refused", request=request)

    monkeypatch.setattr(niimblue, "_request", fail_request)

    status = niimblue.printer_status()

    assert status["configured"] is True
    assert status["service_reachable"] is False
    assert status["connected"] is False
    assert "Connection refused" in status["error"]
