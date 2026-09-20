"""Optional adapter for a local niimblue-node REST print server.

The middleware deliberately does not implement the NIIMBOT wire protocol itself.
Run `niimblue-cli server` on a machine with Bluetooth/serial access and configure
this adapter through NIIMBLUE_* environment variables.
"""

from __future__ import annotations

import os

import httpx


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name, default) or default).strip()


def config() -> dict:
    return {
        "url": _env("NIIMBLUE_URL").rstrip("/"),
        "transport": _env("NIIMBLUE_TRANSPORT", "ble").lower(),
        "address": _env("NIIMBLUE_ADDRESS"),
        "print_task": _env("NIIMBLUE_PRINT_TASK", "D110M_V4"),
        "print_direction": _env("NIIMBLUE_PRINT_DIRECTION", "top"),
        "density": max(1, int(_env("NIIMBLUE_DENSITY", "3") or "3")),
        "label_type": max(1, int(_env("NIIMBLUE_LABEL_TYPE", "1") or "1")),
        "dpi": max(100, int(_env("NIIMBLUE_DPI", "300") or "300")),
        "max_label_width_mm": max(1.0, float(_env("NIIMBLUE_MAX_LABEL_WIDTH_MM", "50") or "50")),
        "timeout": max(1.0, float(_env("NIIMBLUE_TIMEOUT", "30") or "30")),
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


def printer_status() -> dict:
    cfg = config()
    result = {
        "configured": is_configured(),
        "connected": False,
        "address": cfg["address"],
        "transport": cfg["transport"],
        "print_task": cfg["print_task"],
    }
    if not result["configured"]:
        return result
    try:
        result["connected"] = bool(_request("GET", "/connected", timeout=3).json().get("connected"))
        if result["connected"]:
            try:
                result["info"] = _request("GET", "/info", timeout=5).json()
            except Exception:
                pass
    except Exception as exc:
        result["error"] = str(exc)
    return result


def ensure_connected() -> None:
    cfg = config()
    if not is_configured():
        raise RuntimeError("NIIMBOT printing is not configured")
    try:
        connected = bool(_request("GET", "/connected", timeout=3).json().get("connected"))
    except Exception:
        connected = False
    if connected:
        return
    _request(
        "POST",
        "/connect",
        json={"transport": cfg["transport"], "address": cfg["address"]},
        timeout=15,
    )


def print_image_base64(
    image_base64: str,
    *,
    width_mm: float,
    height_mm: float,
    quantity: int = 1,
) -> dict:
    """Print one already-rendered label image through niimblue-node."""
    cfg = config()
    if width_mm <= 0 or height_mm <= 0:
        raise ValueError("Label dimensions must be positive")
    if width_mm > cfg["max_label_width_mm"] + 0.01:
        raise ValueError(
            f"Label is {width_mm:g} mm wide, but the configured printer limit is "
            f"{cfg['max_label_width_mm']:g} mm"
        )
    ensure_connected()
    px_per_mm = cfg["dpi"] / 25.4
    payload = {
        "printDirection": cfg["print_direction"],
        "printTask": cfg["print_task"],
        "quantity": max(1, min(int(quantity), 99)),
        "labelType": cfg["label_type"],
        "density": cfg["density"],
        "imageBase64": image_base64,
        "labelWidth": max(1, round(width_mm * px_per_mm)),
        "labelHeight": max(1, round(height_mm * px_per_mm)),
        "imageFit": "fill",
        "imagePosition": "centre",
        "threshold": 128,
    }
    response = _request("POST", "/print", json=payload, timeout=cfg["timeout"])
    try:
        data = response.json()
    except ValueError:
        data = {"message": response.text or "Printed"}
    return {"ok": True, "response": data, "pixels": [payload["labelWidth"], payload["labelHeight"]]}
