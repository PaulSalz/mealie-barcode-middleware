"""Optional adapter for a local niimblue-node REST print server.

Environment variables remain the defaults. Admin UI overrides are stored in the
application database so printer settings can be changed without restarting B2M.

The label UI deliberately controls connection state. Printing never auto-connects:
this keeps the B21 available for the official niim.blue Web Bluetooth UI when B2M
is not using it.
"""

from __future__ import annotations

import os

import httpx


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name, default) or default).strip()


def _runtime_overrides() -> dict[str, str]:
    try:
        from app.database import SessionLocal
        from app.models import SystemState

        db = SessionLocal()
        try:
            rows = db.query(SystemState).filter(SystemState.key.like("niimblue.%")).all()
            return {row.key.split(".", 1)[1]: row.value or "" for row in rows}
        finally:
            db.close()
    except Exception:
        return {}


def _value(overrides: dict[str, str], key: str, env_name: str, default: str = "") -> str:
    if key in overrides:
        return (overrides[key] or "").strip()
    return _env(env_name, default)


def config() -> dict:
    overrides = _runtime_overrides()
    return {
        "url": _value(overrides, "url", "NIIMBLUE_URL").rstrip("/"),
        "transport": _value(overrides, "transport", "NIIMBLUE_TRANSPORT", "ble").lower(),
        "address": _value(overrides, "address", "NIIMBLUE_ADDRESS"),
        "print_task": _value(overrides, "print_task", "NIIMBLUE_PRINT_TASK", "D110M_V4"),
        "print_direction": _value(overrides, "print_direction", "NIIMBLUE_PRINT_DIRECTION", "top"),
        "density": max(1, int(_value(overrides, "density", "NIIMBLUE_DENSITY", "3") or "3")),
        "label_type": max(1, int(_value(overrides, "label_type", "NIIMBLUE_LABEL_TYPE", "1") or "1")),
        "dpi": max(100, int(_value(overrides, "dpi", "NIIMBLUE_DPI", "300") or "300")),
        "max_label_width_mm": max(1.0, float(_value(overrides, "max_label_width_mm", "NIIMBLUE_MAX_LABEL_WIDTH_MM", "50") or "50")),
        "timeout": max(1.0, float(_value(overrides, "timeout", "NIIMBLUE_TIMEOUT", "30") or "30")),
    }


def is_configured() -> bool:
    cfg = config()
    return bool(cfg["url"] and cfg["address"] and cfg["transport"] in {"ble", "serial"})


def _request(method: str, path: str, *, json: dict | None = None, timeout: float | None = None) -> httpx.Response:
    cfg = config()
    if not cfg["url"]:
        raise RuntimeError("NIIMBLUE_URL is not configured")
    response = httpx.request(method, f"{cfg['url']}{path}", json=json, timeout=timeout or cfg["timeout"])
    response.raise_for_status()
    return response


def _connected() -> bool:
    try:
        return bool(_request("GET", "/connected", timeout=3).json().get("connected"))
    except Exception:
        return False


def printer_status() -> dict:
    cfg = config()
    result = {
        "configured": is_configured(),
        "connected": False,
        "address": cfg["address"],
        "transport": cfg["transport"],
        "print_task": cfg["print_task"],
        "dpi": cfg["dpi"],
        "max_label_width_mm": cfg["max_label_width_mm"],
    }
    if not result["configured"]:
        return result
    try:
        result["connected"] = bool(_request("GET", "/connected", timeout=3).json().get("connected"))
        if result["connected"]:
            try:
                info = _request("GET", "/info", timeout=5).json()
                result["info"] = info
                metadata = info.get("modelMetadata") or {}
                if metadata.get("dpi"):
                    result["dpi"] = metadata["dpi"]
                if info.get("detectedPrintTask"):
                    result["detected_print_task"] = info["detectedPrintTask"]
            except Exception:
                pass
    except Exception as exc:
        result["error"] = str(exc)
    return result


def connect_printer() -> dict:
    cfg = config()
    if not is_configured():
        raise RuntimeError("NIIMBOT printing is not configured")
    if _connected():
        result = printer_status()
        result["message"] = "Already connected"
        return result
    _request(
        "POST",
        "/connect",
        json={"transport": cfg["transport"], "address": cfg["address"]},
        timeout=20,
    )
    result = printer_status()
    result["message"] = "Connected"
    return result


def disconnect_printer() -> dict:
    cfg = config()
    if not cfg["url"]:
        raise RuntimeError("NIIMBLUE_URL is not configured")
    if _connected():
        _request("POST", "/disconnect", json={}, timeout=10)
    result = printer_status()
    result["message"] = "Disconnected"
    return result


def printer_rfid() -> dict:
    if not is_configured():
        raise RuntimeError("NIIMBOT printing is not configured")
    if not _connected():
        raise RuntimeError("B21 Pro is not connected")
    return _request("GET", "/rfid", timeout=8).json()


def _require_connected() -> None:
    if not is_configured():
        raise RuntimeError("NIIMBOT printing is not configured")
    if not _connected():
        raise RuntimeError("B21 Pro is not connected. Connect it from the label page first.")


def print_image_base64(
    image_base64: str,
    *,
    width_mm: float,
    height_mm: float,
    quantity: int = 1,
    density: int | None = None,
    label_type: int | None = None,
    dpi: int | None = None,
    threshold: int = 128,
    print_direction: str | None = None,
    print_task: str | None = None,
) -> dict:
    """Print one already-rendered label image through niimblue-node.

    Connection state is intentionally manual; this function refuses to print when
    the printer is disconnected instead of silently claiming the BLE connection.
    """
    cfg = config()
    if width_mm <= 0 or height_mm <= 0:
        raise ValueError("Label dimensions must be positive")
    if width_mm > cfg["max_label_width_mm"] + 0.01:
        raise ValueError(
            f"Label is {width_mm:g} mm wide, but the configured printer limit is "
            f"{cfg['max_label_width_mm']:g} mm"
        )
    _require_connected()

    resolved_dpi = max(100, min(int(dpi or cfg["dpi"]), 1200))
    resolved_density = max(1, min(int(density or cfg["density"]), 5))
    resolved_label_type = max(1, int(label_type or cfg["label_type"]))
    resolved_threshold = max(1, min(int(threshold or 128), 255))
    px_per_mm = resolved_dpi / 25.4
    payload = {
        "printDirection": print_direction or cfg["print_direction"],
        "printTask": print_task or cfg["print_task"],
        "quantity": max(1, min(int(quantity), 99)),
        "labelType": resolved_label_type,
        "density": resolved_density,
        "imageBase64": image_base64,
        "labelWidth": max(8, round(width_mm * px_per_mm)),
        "labelHeight": max(8, round(height_mm * px_per_mm)),
        "imageFit": "fill",
        "imagePosition": "centre",
        "threshold": resolved_threshold,
    }
    response = _request("POST", "/print", json=payload, timeout=cfg["timeout"])
    try:
        data = response.json()
    except ValueError:
        data = {"message": response.text or "Printed"}
    return {
        "ok": True,
        "response": data,
        "pixels": [payload["labelWidth"], payload["labelHeight"]],
        "density": resolved_density,
        "label_type": resolved_label_type,
    }
