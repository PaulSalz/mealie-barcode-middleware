#!/usr/bin/env python3
"""USB HID barcode scanner bridge for Mealie Barcode Middleware.

The bridge deliberately knows nothing about FOOD:, RECIPE:, GENERIC:, ACTION:,
etc. It only decodes the HID keyboard stream into a full string and POSTs it
to /scan. Business logic stays in the middleware.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request

from evdev import InputDevice, ecodes

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("barcode2mealie-usb")

DEFAULT_DEVICE = "/dev/input/by-id/usb-Jieli_Technology_Receive-HID_415035383237330C-event-kbd"

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


def api_token() -> str:
    token = _env("MIDDLEWARE_TOKEN", "MIDDLEWARE_API_TOKEN", "BARCODE_API_TOKEN", "API_TOKEN", "API_KEY")
    if not token:
        raise RuntimeError(
            "No middleware API token configured. Set MIDDLEWARE_TOKEN (or MIDDLEWARE_API_TOKEN/API_TOKEN)."
        )
    return token


def post_barcode(barcode: str) -> None:
    payload = json.dumps({"barcode": barcode}).encode("utf-8")
    request = urllib.request.Request(
        scan_url(),
        data=payload,
        method="POST",
        headers={
            "Authorization": "Bearer " + api_token(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    timeout = float(_env("HTTP_TIMEOUT", default="8") or "8")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
            elapsed = int((time.monotonic() - started) * 1000)
            log.info("scan=%r HTTP %d in %d ms response=%s", barcode, response.status, elapsed, body[:300])
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        log.error("scan=%r HTTP %d response=%s", barcode, exc.code, body[:500])
    except Exception:
        log.exception("scan=%r POST failed", barcode)


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


def main() -> int:
    device_path = _env("SCANNER_DEVICE", "BARCODE_DEVICE", default=DEFAULT_DEVICE) or DEFAULT_DEVICE
    min_length = int(_env("MIN_BARCODE_LENGTH", default="1") or "1")
    max_length = int(_env("MAX_BARCODE_LENGTH", default="256") or "256")
    layout = (_env("SCANNER_KEYBOARD_LAYOUT", default="de") or "de").strip().lower()
    if layout not in {"de", "us"}:
        raise RuntimeError("SCANNER_KEYBOARD_LAYOUT must be 'de' or 'us'")

    device = InputDevice(device_path)
    log.info("Listening on %s (%s), layout=%s, posting to %s", device_path, device.name, layout, scan_url())

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

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
    except Exception as exc:
        log.exception("Scanner bridge stopped: %s", exc)
        raise SystemExit(1)
