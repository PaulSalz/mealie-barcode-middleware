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



def test_scan_printer_devices_forwards_discovery_options(monkeypatch):
    cfg = {
        "url": "http://niimblue-node:5000",
        "transport": "ble",
        "address": "",
        "print_task": "D110M_V4",
        "dpi": 300,
        "max_label_width_mm": 50,
    }
    captured = {}
    monkeypatch.setattr(niimblue, "config", lambda: cfg)

    class Response:
        def json(self):
            return {"devices": [{"name": "B21 Pro", "address": "AA:BB:CC:DD:EE:FF"}]}

    def fake_request(method, path, **kwargs):
        captured.update(method=method, path=path, **kwargs)
        return Response()

    monkeypatch.setattr(niimblue, "_request", fake_request)

    result = niimblue.scan_printer_devices(transport="BLE", timeout_ms=8000)

    assert result["devices"][0]["address"] == "AA:BB:CC:DD:EE:FF"
    assert captured["method"] == "POST"
    assert captured["path"] == "/scan"
    assert captured["json"] == {"transport": "ble", "timeout": 8000}
    assert captured["timeout"] == 13
