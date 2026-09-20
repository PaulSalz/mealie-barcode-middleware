#!/usr/bin/env python3
"""USB HID barcode scanner bridge for Mealie Barcode Middleware.

The bridge deliberately knows nothing about FOOD:, RECIPE:, GENERIC:, ACTION:,
etc. It only decodes the HID keyboard stream into a full string and POSTs it
to /scan. Business logic stays in the middleware.
"""

import glob
import json
import logging
import os
import socket
import threading
import time
import urllib.error
import urllib.request

from evdev import InputDevice, ecodes

SCANNER_VERSION = "2.2.1"
STARTED_MONO = time.monotonic()
_stats_lock = threading.Lock()
_stats = {"scans": 0, "errors": 0, "last_latency_ms": 0}
_runtime = {"device": "disconnected", "layout": "de"}

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("barcode2mealie-usb")

DEFAULT_DEVICE = "/dev/input/by-id/usb-Jieli_Technology_Receive-HID_415035383237330C-event-kbd"
AUTO_DEVICE_GLOBS = (
    "/dev/input/by-id/*Jieli*event-kbd",
    "/dev/input/by-id/*Receive-HID*event-kbd",
)

US_NORMAL = {
    "KEY_1": "1", "KEY_2": "2", "KEY_3": "3", "KEY_4": "4", "KEY_5": "5",
    "KEY_6": "6", "KEY_7": "7", "KEY_8": "8", "KEY_9": "9", "KEY_0": "0",
    "KEY_MINUS": "-", "KEY_EQUAL": "=", "KEY_LEFTBRACE": "[", "KEY_RIGHTBRACE": "]",
    "KEY_BACKSLASH": "\\", "KEY_SEMICOLON": ";", "KEY_APOSTROPHE": "'", "KEY_GRAVE": "`",
    "KEY_COMMA": ",", "KEY_DOT": ".", "KEY_SLASH": "/", "KEY_SPACE": " ",
}
US_SHIFT = {
    "KEY_1": "!", "KEY_2": "@", "KEY_3": "#", "KEY_4": "$", "KEY_5": "%",
    "KEY_6": "^", "KEY_7": "&", "KEY_8": "*", "KEY_9": "(", "KEY_0": ")",
    "KEY_MINUS": "_", "KEY_EQUAL": "+", "KEY_LEFTBRACE": "{", "KEY_RIGHTBRACE": "}",
    "KEY_BACKSLASH": "|", "KEY_SEMICOLON": ":", "KEY_APOSTROPHE": '"', "KEY_GRAVE": "~",
    "KEY_COMMA": "<", "KEY_DOT": ">", "KEY_SLASH": "?", "KEY_SPACE": " ",
}

DE_NORMAL = {
    "KEY_1": "1", "KEY_2": "2", "KEY_3": "3", "KEY_4": "4", "KEY_5": "5",
    "KEY_6": "6", "KEY_7": "7", "KEY_8": "8", "KEY_9": "9", "KEY_0": "0",
    "KEY_MINUS": "ß", "KEY_EQUAL": "´", "KEY_LEFTBRACE": "ü", "KEY_RIGHTBRACE": "+",
    "KEY_BACKSLASH": "#", "KEY_SEMICOLON": "ö", "KEY_APOSTROPHE": "ä", "KEY_GRAVE": "^",
    "KEY_COMMA": ",", "KEY_DOT": ".", "KEY_SLASH": "-", "KEY_SPACE": " ",
}
DE_SHIFT = {
    "KEY_1": "!", "KEY_2": '"', "KEY_3": "§", "KEY_4": "$", "KEY_5": "%",
    "KEY_6": "&", "KEY_7": "/", "KEY_8": "(", "KEY_9": ")", "KEY_0": "=",
    "KEY_MINUS": "?", "KEY_EQUAL": "`", "KEY_LEFTBRACE": "Ü", "KEY_RIGHTBRACE": "*",
    "KEY_BACKSLASH": "'", "KEY_SEMICOLON": "Ö", "KEY_APOSTROPHE": "Ä", "KEY_GRAVE": "°",
    "KEY_COMMA": ";", "KEY_DOT": ":", "KEY_SLASH": "_", "KEY_SPACE": " ",
}
DE_ALTGR = {
    "KEY_Q": "@", "KEY_E": "€", "KEY_7": "{", "KEY_8": "[", "KEY_9": "]",
    "KEY_0": "}", "KEY_MINUS": "\\", "KEY_RIGHTBRACE": "~",
}

KEYPAD = {
    "KEY_KP0": "0", "KEY_KP1": "1", "KEY_KP2": "2", "KEY_KP3": "3", "KEY_KP4": "4",
    "KEY_KP5": "5", "KEY_KP6": "6", "KEY_KP7": "7", "KEY_KP8": "8", "KEY_KP9": "9",
    "KEY_KPDOT": ".", "KEY_KPSLASH": "/", "KEY_KPASTERISK": "*", "KEY_KPMINUS": "-", "KEY_KPPLUS": "+",
}

for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    US_NORMAL[f"KEY_{letter}"] = letter.lower()
    US_SHIFT[f"KEY_{letter}"] = letter
    de_letter = "z" if letter == "Y" else "y" if letter == "Z" else letter.lower()
    DE_NORMAL[f"KEY_{letter}"] = de_letter
    DE_SHIFT[f"KEY_{letter}"] = de_letter.upper()

ENTER_KEYS = {"KEY_ENTER", "KEY_KPENTER"}
SHIFT_KEYS = {"KEY_LEFTSHIFT", "KEY_RIGHTSHIFT"}
ALTGR_KEYS = {"KEY_RIGHTALT"}


def _env(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


def scan_url() -> str:
    explicit = _env("SCAN_URL", "MIDDLEWARE_SCAN_URL")
    if explicit:
        return explicit.rstrip("/")
    base = _env("MIDDLEWARE_URL", default="http://127.0.0.1:9930") or "http://127.0.0.1:9930"
    base = base.rstrip("/")
    return base if base.endswith("/scan") else base + "/scan"


def heartbeat_url() -> str:
    explicit = _env("SCANNER_HEARTBEAT_URL")
    if explicit:
        return explicit.rstrip("/")
    url = scan_url()
    return url[:-5] + "/scanner/heartbeat" if url.endswith("/scan") else url.rstrip("/") + "/scanner/heartbeat"


def api_token() -> str:
    token = _env("MIDDLEWARE_TOKEN", "MIDDLEWARE_API_TOKEN", "BARCODE_API_TOKEN", "API_TOKEN", "API_KEY")
    if not token:
        raise RuntimeError("No middleware API token configured. Set MIDDLEWARE_TOKEN (or MIDDLEWARE_API_TOKEN/API_TOKEN).")
    return token


def telemetry_headers() -> dict[str, str]:
    with _stats_lock:
        stats = dict(_stats)
    return {
        "Authorization": "Bearer " + api_token(),
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-B2M-Scanner-Version": SCANNER_VERSION,
        "X-B2M-Scanner-Hostname": socket.gethostname(),
        "X-B2M-Scanner-Device": _runtime["device"],
        "X-B2M-Scanner-Layout": _runtime["layout"],
        "X-B2M-Scanner-Uptime": str(int(time.monotonic() - STARTED_MONO)),
        "X-B2M-Scanner-Scans": str(stats["scans"]),
        "X-B2M-Scanner-Errors": str(stats["errors"]),
        "X-B2M-Scanner-Last-Latency": str(stats["last_latency_ms"]),
    }


def _post(url: str, payload: dict, *, count_scan: bool = False, log_scan: str | None = None) -> bool:
    if count_scan:
        with _stats_lock:
            _stats["scans"] += 1
    timeout = float(_env("HTTP_TIMEOUT", default="8") or "8")
    started = time.monotonic()
    try:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers=telemetry_headers(),
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
            elapsed = int((time.monotonic() - started) * 1000)
            with _stats_lock:
                _stats["last_latency_ms"] = elapsed
            if log_scan is not None:
                log.info("scan=%r HTTP %d in %d ms response=%s", log_scan, response.status, elapsed, body[:300])
            return True
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        if count_scan:
            with _stats_lock:
                _stats["errors"] += 1
        if log_scan is not None:
            log.error("scan=%r HTTP %d response=%s", log_scan, exc.code, body[:500])
        else:
            log.debug("heartbeat HTTP %d response=%s", exc.code, body[:200])
    except Exception:
        if count_scan:
            with _stats_lock:
                _stats["errors"] += 1
        if log_scan is not None:
            log.exception("scan=%r POST failed", log_scan)
        else:
            log.debug("scanner heartbeat failed", exc_info=True)
    return False


def post_barcode(barcode: str) -> None:
    _post(scan_url(), {"barcode": barcode}, count_scan=True, log_scan=barcode)


def heartbeat_loop(interval: float) -> None:
    # Heartbeats deliberately continue while the USB scanner is unplugged so the
    # middleware can distinguish a running bridge from a dead service.
    while True:
        _post(heartbeat_url(), {}, count_scan=False)
        time.sleep(interval)


def decode_key(key_name: str, shifted: bool, altgr: bool, layout: str) -> str | None:
    if key_name in KEYPAD:
        return KEYPAD[key_name]
    if layout == "de":
        if altgr and key_name in DE_ALTGR:
            return DE_ALTGR[key_name]
        table = DE_SHIFT if shifted else DE_NORMAL
        return table.get(key_name) or DE_NORMAL.get(key_name)
    table = US_SHIFT if shifted else US_NORMAL
    return table.get(key_name) or US_NORMAL.get(key_name)


def resolve_device_path(device_spec: str) -> str | None:
    """Resolve an explicit device path or auto-discover the Jieli HID scanner."""
    spec = (device_spec or "auto").strip()
    if spec.lower() != "auto":
        return spec if os.path.exists(spec) else None

    candidates: list[str] = []
    if os.path.exists(DEFAULT_DEVICE):
        candidates.append(DEFAULT_DEVICE)
    for pattern in AUTO_DEVICE_GLOBS:
        candidates.extend(glob.glob(pattern))

    unique = sorted(dict.fromkeys(path for path in candidates if os.path.exists(path)))
    return unique[0] if unique else None


def _read_device(device: InputDevice, layout: str, min_length: int, max_length: int) -> None:
    buffer: list[str] = []
    shift_down = False
    altgr_down = False

    for event in device.read_loop():
        if event.type != ecodes.EV_KEY:
            continue
        key_name = ecodes.KEY.get(event.code, "")
        if isinstance(key_name, list):
            key_name = key_name[0] if key_name else ""
        key_name = str(key_name)

        if key_name in SHIFT_KEYS:
            shift_down = event.value != 0
            continue
        if key_name in ALTGR_KEYS:
            altgr_down = event.value != 0
            continue
        if event.value != 1:
            continue

        if key_name in ENTER_KEYS:
            value = "".join(buffer).strip()
            buffer.clear()
            if len(value) < min_length:
                if value:
                    log.warning("Ignoring too-short scan: %r", value)
                continue
            if len(value) > max_length:
                log.warning("Ignoring too-long scan (%d chars)", len(value))
                continue
            post_barcode(value)
            continue

        if key_name == "KEY_BACKSPACE":
            if buffer:
                buffer.pop()
            continue
        if key_name == "KEY_ESC":
            buffer.clear()
            continue

        char = decode_key(key_name, shift_down, altgr_down, layout)
        if char is not None and len(buffer) < max_length:
            buffer.append(char)
        elif char is None:
            log.debug("Unhandled HID key: %s", key_name)


def main() -> int:
    device_spec = _env("SCANNER_DEVICE", "BARCODE_DEVICE", default="auto") or "auto"
    min_length = int(_env("MIN_BARCODE_LENGTH", default="1") or "1")
    max_length = int(_env("MAX_BARCODE_LENGTH", default="256") or "256")
    layout = (_env("SCANNER_KEYBOARD_LAYOUT", default="de") or "de").strip().lower()
    heartbeat_interval = float(_env("HEARTBEAT_INTERVAL", default="60") or "60")
    reconnect_interval = max(0.5, float(_env("SCANNER_RECONNECT_INTERVAL", default="2") or "2"))
    if layout not in {"de", "us"}:
        raise RuntimeError("SCANNER_KEYBOARD_LAYOUT must be 'de' or 'us'")

    # Validate the token up front. Missing scanner hardware is tolerated; missing
    # authentication is a real configuration error and should still fail loudly.
    api_token()
    _runtime["layout"] = layout
    _runtime["device"] = "disconnected"

    log.info(
        "Scanner bridge v%s starting, device=%s, layout=%s, posting to %s",
        SCANNER_VERSION, device_spec, layout, scan_url(),
    )

    if heartbeat_interval > 0:
        threading.Thread(target=heartbeat_loop, args=(max(15.0, heartbeat_interval),), daemon=True).start()

    waiting_logged = False
    while True:
        device_path = resolve_device_path(device_spec)
        if not device_path:
            _runtime["device"] = "disconnected"
            if not waiting_logged:
                log.warning("Scanner not connected; waiting for USB device (device=%s)", device_spec)
                waiting_logged = True
            time.sleep(reconnect_interval)
            continue

        device = None
        try:
            device = InputDevice(device_path)
            _runtime["device"] = device_path
            waiting_logged = False
            log.info(
                "Scanner connected on %s (%s), layout=%s",
                device_path, device.name, layout,
            )
            _read_device(device, layout, min_length, max_length)
            log.warning("Scanner device %s closed; waiting for reconnect", device_path)
        except (FileNotFoundError, OSError) as exc:
            _runtime["device"] = "disconnected"
            if not waiting_logged:
                log.warning("Scanner unavailable/disconnected: %s; waiting for reconnect", exc)
                waiting_logged = True
        finally:
            _runtime["device"] = "disconnected"
            if device is not None:
                try:
                    device.close()
                except Exception:
                    pass

        time.sleep(reconnect_interval)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
    except Exception as exc:
        log.exception("Scanner bridge stopped: %s", exc)
        raise SystemExit(1)
