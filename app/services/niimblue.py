"""Optional adapter for a local niimblue-node REST print server.

Environment variables remain the defaults. Admin UI overrides are stored in the
application database so printer settings can be changed without restarting B2M.

The label UI deliberately controls connection state. Printing never auto-connects:
this keeps the B21 available for the official niim.blue Web Bluetooth UI when B2M
is not using it.
"""

from __future__ import annotations

import os
import threading
import time

import httpx

_http = httpx.Client(
    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5, keepalive_expiry=60.0),
)
# A physical printer can execute only one print stream at a time. Keep this at
# the adapter layer so queued label jobs, shopping receipts and direct print
# requests can never race each other even if they arrive through different APIs.
_print_lock = threading.Lock()


class PrintOutcomeUnknown(RuntimeError):
    """The print request was sent, but its final outcome could not be confirmed."""


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


def _request(method: str, path: str, *, json: dict | None = None, timeout: float | httpx.Timeout | None = None) -> httpx.Response:
    cfg = config()
    if not cfg["url"]:
        raise RuntimeError("NIIMBLUE_URL is not configured")
    response = _http.request(method, f"{cfg['url']}{path}", json=json, timeout=timeout or cfg["timeout"])
    response.raise_for_status()
    return response


def _http_error_message(exc: Exception, *, action: str = "request") -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        detail = ""
        try:
            payload = response.json()
            if isinstance(payload, dict):
                detail = str(payload.get("error") or payload.get("message") or "").strip()
            elif payload is not None:
                detail = str(payload).strip()
        except ValueError:
            detail = (response.text or "").strip()
        detail = " ".join(detail.split())[:350]
        suffix = f": {detail}" if detail else ""
        return f"niimblue-node {action} failed (HTTP {response.status_code}){suffix}"
    if isinstance(exc, httpx.TimeoutException):
        return f"niimblue-node {action} timed out"
    if isinstance(exc, httpx.HTTPError):
        return f"niimblue-node {action} failed: {exc.__class__.__name__}"
    return str(exc)


def _connected(*, timeout: float = 2.0) -> bool:
    """Confirm connection state once more before reporting a transient disconnect."""
    for attempt in range(2):
        try:
            if bool(_request("GET", "/connected", timeout=timeout if attempt == 0 else min(timeout, 1.2)).json().get("connected")):
                return True
        except Exception:
            pass
        if attempt == 0:
            time.sleep(0.12)
    return False


def _wait_connected(seconds: float = 3.0) -> bool:
    deadline = time.monotonic() + max(0.2, seconds)
    while time.monotonic() < deadline:
        if _connected(timeout=1.0):
            return True
        time.sleep(0.2)
    return _connected(timeout=1.0)


def _media_from_rfid_payload(payload: dict | None) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    paper = payload.get("paperRfidInfo") if isinstance(payload.get("paperRfidInfo"), dict) else {}
    raw_type = paper.get("consumablesType")
    try:
        label_type = int(raw_type)
    except (TypeError, ValueError):
        label_type = 0
    if label_type <= 0:
        label_type = None
    return {
        "tag_present": bool(paper.get("tagPresent")),
        "barcode": str(paper.get("barCode") or "").strip(),
        "uuid": str(paper.get("uuid") or "").strip(),
        "label_type": label_type,
    }


def detected_media() -> dict:
    """Best-effort information about the currently inserted RFID media.

    niimblue-node exposes ``paperRfidInfo.consumablesType`` using the same
    LabelType enum used by the print protocol. Prefer this value over a stale UI
    profile whenever a valid RFID tag is present.
    """
    if not is_configured() or not _connected():
        return {"tag_present": False, "barcode": "", "uuid": "", "label_type": None}
    try:
        return _media_from_rfid_payload(_request("GET", "/rfid", timeout=5).json())
    except Exception:
        return {"tag_present": False, "barcode": "", "uuid": "", "label_type": None}


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
        result["connected"] = _connected(timeout=1.5)
        if result["connected"]:
            try:
                info = _request("GET", "/info", timeout=4).json()
                result["info"] = info
                metadata = info.get("modelMetadata") or {}
                if metadata.get("dpi"):
                    result["dpi"] = metadata["dpi"]
                if info.get("detectedPrintTask"):
                    result["detected_print_task"] = info["detectedPrintTask"]
            except Exception as exc:
                result["info_error"] = _http_error_message(exc, action="info request")
            media = detected_media()
            if media.get("tag_present"):
                result["media"] = media
    except Exception as exc:
        result["error"] = _http_error_message(exc, action="status request")
    return result


def _disconnect_best_effort() -> None:
    try:
        _request("POST", "/disconnect", json={}, timeout=2.5)
    except Exception:
        pass


def _connect_once(payload: dict, *, timeout: float = 8.0) -> Exception | None:
    try:
        _request("POST", "/connect", json=payload, timeout=timeout)
        return None
    except Exception as exc:
        return exc


def connect_printer() -> dict:
    cfg = config()
    if not is_configured():
        raise RuntimeError("NIIMBOT printing is not configured")
    if _connected():
        result = printer_status()
        result["message"] = "Already connected"
        return result

    payload = {"transport": cfg["transport"], "address": cfg["address"]}
    # Clear a stale niimblue-node transport state first. This is cheap when
    # disconnected and avoids the common transient "Disconnected 62" BLE state.
    _disconnect_best_effort()
    time.sleep(0.15)

    first_error = _connect_once(payload, timeout=min(cfg["timeout"], 8.0))
    if first_error is None and _wait_connected(3.0):
        result = printer_status()
        result["message"] = "Connected"
        return result
    if first_error is not None and _wait_connected(0.5):
        result = printer_status()
        result["message"] = "Connected"
        return result

    # One bounded retry is useful for BLE after a browser/direct connection was
    # released only moments ago. Do not leave the HTTP request hanging forever.
    _disconnect_best_effort()
    time.sleep(0.3)
    retry_error = _connect_once(payload, timeout=min(cfg["timeout"], 8.0))
    if _wait_connected(3.5):
        result = printer_status()
        result["message"] = "Connected"
        return result

    error = retry_error or first_error
    if error is not None:
        raise RuntimeError(_http_error_message(error, action="connect")) from error
    raise RuntimeError(
        f"niimblue-node accepted Connect for {cfg['address']}, but the printer did not become connected"
    )


def disconnect_printer() -> dict:
    cfg = config()
    if not cfg["url"]:
        raise RuntimeError("NIIMBLUE_URL is not configured")
    # Always ask niimblue-node to disconnect. /connected can briefly return a
    # stale false value while BLE is still occupied, which must not block recovery.
    try:
        _request("POST", "/disconnect", json={}, timeout=5)
    except httpx.HTTPError as exc:
        raise RuntimeError(_http_error_message(exc, action="disconnect")) from exc
    result = printer_status()
    result["message"] = "Disconnect requested"
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
    All callers share one process-wide print lock because the physical B21 cannot
    execute overlapping print streams.
    """
    cfg = config()
    if width_mm <= 0 or height_mm <= 0:
        raise ValueError("Label dimensions must be positive")
    if width_mm > cfg["max_label_width_mm"] + 0.01:
        raise ValueError(
            f"Label is {width_mm:g} mm wide, but the configured printer limit is "
            f"{cfg['max_label_width_mm']:g} mm"
        )

    resolved_dpi = max(100, min(int(dpi or cfg["dpi"]), 1200))
    resolved_density = max(1, min(int(density or cfg["density"]), 5))
    requested_label_type = max(1, int(label_type or cfg["label_type"]))
    resolved_threshold = max(1, min(int(threshold or 128), 255))
    px_per_mm = resolved_dpi / 25.4

    with _print_lock:
        _require_connected()
        media = detected_media()
        media_label_type = media.get("label_type") if media.get("tag_present") else None
        resolved_label_type = int(media_label_type or requested_label_type)
        payload = {
            "printDirection": print_direction or cfg["print_direction"],
            "printTask": print_task or cfg["print_task"],
            "quantity": max(1, min(int(quantity), 99)),
            "labelType": resolved_label_type,
            "density": resolved_density,
            "imageBase64": image_base64,
            "labelWidth": max(8, round(width_mm * px_per_mm)),
            "labelHeight": max(8, round(height_mm * px_per_mm)),
            # Preserve the source aspect ratio when a bound roll profile changes
            # the physical target size. 'fill' stretched smaller-roll labels.
            "imageFit": "contain",
            "imagePosition": "centre",
            "threshold": resolved_threshold,
        }
        try:
            response = _request("POST", "/print", json=payload, timeout=cfg["timeout"])
        except httpx.HTTPError as exc:
            raise RuntimeError(_http_error_message(exc, action="print")) from exc

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
        "label_type_source": "rfid" if media.get("tag_present") and media.get("label_type") else "requested",
        "media": media,
    }
