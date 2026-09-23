#!/usr/bin/env python3
"""USB HID barcode scanner bridge for Mealie Barcode Middleware.

HID reading, immediate scan acknowledgements and the potentially slow /scan request
run independently. Physical scans are persisted to a small SQLite outbox before
network delivery, so a B2M restart or temporary network outage cannot silently
lose them. Each delivery carries a stable ID so B2M can replay a completed result
without adding the same item twice after an ambiguous timeout.
"""

import glob
import json
import logging
import os
from pathlib import Path
import queue
import socket
import sqlite3
import threading
import time
import urllib.error
import urllib.request
import uuid

from evdev import InputDevice, ecodes

SCANNER_VERSION = "2.5.0"
STARTED_MONO = time.monotonic()
_stats_lock = threading.Lock()
_stats = {"scans": 0, "errors": 0, "last_latency_ms": 0}
_runtime = {"device": "disconnected", "layout": "de"}
_config_lock = threading.Lock()
_runtime_config = {"min_barcode_length": 4, "scan_queue_size": 64, "scan_key_gap_seconds": 0.4}
_ack_queue: queue.Queue[str] | None = None
_delivery_wakeup = threading.Event()
_outbox_path: str | None = None

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
    "KEY_1":"1","KEY_2":"2","KEY_3":"3","KEY_4":"4","KEY_5":"5","KEY_6":"6","KEY_7":"7","KEY_8":"8","KEY_9":"9","KEY_0":"0",
    "KEY_MINUS":"-","KEY_EQUAL":"=","KEY_LEFTBRACE":"[","KEY_RIGHTBRACE":"]","KEY_BACKSLASH":"\\","KEY_SEMICOLON":";","KEY_APOSTROPHE":"'","KEY_GRAVE":"`","KEY_COMMA":",","KEY_DOT":".","KEY_SLASH":"/","KEY_SPACE":" ",
}
US_SHIFT = {
    "KEY_1":"!","KEY_2":"@","KEY_3":"#","KEY_4":"$","KEY_5":"%","KEY_6":"^","KEY_7":"&","KEY_8":"*","KEY_9":"(","KEY_0":")",
    "KEY_MINUS":"_","KEY_EQUAL":"+","KEY_LEFTBRACE":"{","KEY_RIGHTBRACE":"}","KEY_BACKSLASH":"|","KEY_SEMICOLON":":","KEY_APOSTROPHE":"\"","KEY_GRAVE":"~","KEY_COMMA":"<","KEY_DOT":">","KEY_SLASH":"?","KEY_SPACE":" ",
}
DE_NORMAL = {
    "KEY_1":"1","KEY_2":"2","KEY_3":"3","KEY_4":"4","KEY_5":"5","KEY_6":"6","KEY_7":"7","KEY_8":"8","KEY_9":"9","KEY_0":"0",
    "KEY_MINUS":"ß","KEY_EQUAL":"´","KEY_LEFTBRACE":"ü","KEY_RIGHTBRACE":"+","KEY_BACKSLASH":"#","KEY_SEMICOLON":"ö","KEY_APOSTROPHE":"ä","KEY_GRAVE":"^","KEY_COMMA":",","KEY_DOT":".","KEY_SLASH":"-","KEY_SPACE":" ",
}
DE_SHIFT = {
    "KEY_1":"!","KEY_2":"\"","KEY_3":"§","KEY_4":"$","KEY_5":"%","KEY_6":"&","KEY_7":"/","KEY_8":"(","KEY_9":")","KEY_0":"=",
    "KEY_MINUS":"?","KEY_EQUAL":"`","KEY_LEFTBRACE":"Ü","KEY_RIGHTBRACE":"*","KEY_BACKSLASH":"'","KEY_SEMICOLON":"Ö","KEY_APOSTROPHE":"Ä","KEY_GRAVE":"°","KEY_COMMA":";","KEY_DOT":":","KEY_SLASH":"_","KEY_SPACE":" ",
}
DE_ALTGR = {"KEY_Q":"@","KEY_E":"€","KEY_7":"{","KEY_8":"[","KEY_9":"]","KEY_0":"}","KEY_MINUS":"\\","KEY_RIGHTBRACE":"~"}
KEYPAD = {"KEY_KP0":"0","KEY_KP1":"1","KEY_KP2":"2","KEY_KP3":"3","KEY_KP4":"4","KEY_KP5":"5","KEY_KP6":"6","KEY_KP7":"7","KEY_KP8":"8","KEY_KP9":"9","KEY_KPDOT":".","KEY_KPSLASH":"/","KEY_KPASTERISK":"*","KEY_KPMINUS":"-","KEY_KPPLUS":"+"}

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
    base = (_env("MIDDLEWARE_URL", default="http://127.0.0.1:9930") or "http://127.0.0.1:9930").rstrip("/")
    return base if base.endswith("/scan") else base + "/scan"


def middleware_base_url() -> str:
    url = scan_url()
    return url[:-5] if url.endswith("/scan") else url.rstrip("/")


def heartbeat_url() -> str:
    explicit = _env("SCANNER_HEARTBEAT_URL")
    return explicit.rstrip("/") if explicit else middleware_base_url() + "/scanner/heartbeat"


def received_url() -> str:
    explicit = _env("SCANNER_RECEIVED_URL")
    return explicit.rstrip("/") if explicit else middleware_base_url() + "/scanner/received"


def config_url() -> str:
    explicit = _env("SCANNER_CONFIG_URL")
    return explicit.rstrip("/") if explicit else middleware_base_url() + "/scanner/config"


def api_token() -> str:
    token = _env("MIDDLEWARE_TOKEN", "MIDDLEWARE_API_TOKEN", "BARCODE_API_TOKEN", "API_TOKEN", "API_KEY")
    if not token:
        raise RuntimeError("No middleware API token configured. Set MIDDLEWARE_TOKEN (or MIDDLEWARE_API_TOKEN/API_TOKEN).")
    return token


def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer " + api_token(), "Content-Type": "application/json", "Accept": "application/json"}


def telemetry_headers() -> dict[str, str]:
    with _stats_lock:
        stats = dict(_stats)
    headers = auth_headers()
    headers.update({
        "X-B2M-Scanner-Version": SCANNER_VERSION, "X-B2M-Scanner-Hostname": socket.gethostname(),
        "X-B2M-Scanner-Device": _runtime["device"], "X-B2M-Scanner-Layout": _runtime["layout"],
        "X-B2M-Scanner-Uptime": str(int(time.monotonic() - STARTED_MONO)), "X-B2M-Scanner-Scans": str(stats["scans"]),
        "X-B2M-Scanner-Errors": str(stats["errors"]), "X-B2M-Scanner-Last-Latency": str(stats["last_latency_ms"]),
    })
    return headers


def _post(
    url: str,
    payload: dict,
    *,
    log_scan: str | None = None,
    timeout_override: float | None = None,
    include_telemetry: bool = True,
    track_delivery: bool = False,
    extra_headers: dict[str, str] | None = None,
) -> bool:
    timeout = timeout_override if timeout_override is not None else float(_env("HTTP_TIMEOUT", default="8") or "8")
    headers = telemetry_headers() if include_telemetry else auth_headers()
    if extra_headers:
        headers.update(extra_headers)
    started = time.monotonic()
    try:
        request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST", headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
            elapsed = int((time.monotonic() - started) * 1000)
            if track_delivery:
                with _stats_lock:
                    _stats["last_latency_ms"] = elapsed
            if log_scan is not None:
                log.info("scan=%r HTTP %d in %d ms response=%s", log_scan, response.status, elapsed, body[:300])
            return 200 <= response.status < 300
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        if track_delivery:
            with _stats_lock:
                _stats["errors"] += 1
        if log_scan is not None:
            log.warning("scan=%r HTTP %d response=%s", log_scan, exc.code, body[:500])
        else:
            log.debug("auxiliary POST HTTP %d response=%s", exc.code, body[:200])
    except Exception:
        if track_delivery:
            with _stats_lock:
                _stats["errors"] += 1
        if log_scan is not None:
            log.warning("scan=%r POST failed", log_scan, exc_info=True)
        else:
            log.debug("scanner auxiliary POST failed", exc_info=True)
    return False


def _get_json(url: str, timeout: float = 2.0) -> dict | None:
    try:
        request = urllib.request.Request(url, method="GET", headers=auth_headers())
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", "replace"))
            return data if isinstance(data, dict) else None
    except Exception:
        log.debug("scanner config refresh failed", exc_info=True)
        return None


def _candidate_outbox_paths() -> list[Path]:
    explicit = _env("SCANNER_OUTBOX_PATH")
    if explicit:
        return [Path(explicit).expanduser()]
    return [
        Path("/var/lib/barcode2mealie/scanner-outbox.db"),
        Path(__file__).resolve().with_name("scanner-outbox.db"),
        Path.home() / ".local/state/barcode2mealie/scanner-outbox.db",
    ]


def _init_outbox() -> None:
    global _outbox_path
    last_error: Exception | None = None
    for candidate in _candidate_outbox_paths():
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(candidate), timeout=5.0)
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA busy_timeout=5000")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scan_outbox (
                        delivery_id TEXT PRIMARY KEY,
                        barcode TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        next_attempt REAL NOT NULL DEFAULT 0
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()
            _outbox_path = str(candidate)
            return
        except (OSError, sqlite3.Error) as exc:
            last_error = exc
            if _env("SCANNER_OUTBOX_PATH"):
                break
    raise RuntimeError(f"Could not initialize persistent scanner outbox: {last_error}")


def _outbox_connect() -> sqlite3.Connection:
    if not _outbox_path:
        raise RuntimeError("scanner outbox is not initialized")
    conn = sqlite3.connect(_outbox_path, timeout=5.0)
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _outbox_count() -> int:
    conn = _outbox_connect()
    try:
        row = conn.execute("SELECT COUNT(*) FROM scan_outbox").fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def _outbox_enqueue(barcode: str, capacity: int) -> str | None:
    conn = _outbox_connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        count = int(conn.execute("SELECT COUNT(*) FROM scan_outbox").fetchone()[0])
        if count >= capacity:
            conn.rollback()
            return None
        delivery_id = uuid.uuid4().hex
        now = time.time()
        conn.execute(
            "INSERT INTO scan_outbox(delivery_id, barcode, created_at, attempts, next_attempt) VALUES (?, ?, ?, 0, ?)",
            (delivery_id, barcode, now, now),
        )
        conn.commit()
        return delivery_id
    finally:
        conn.close()


def _outbox_next() -> tuple[str, str, int] | None:
    conn = _outbox_connect()
    try:
        row = conn.execute(
            "SELECT delivery_id, barcode, attempts FROM scan_outbox WHERE next_attempt <= ? ORDER BY created_at, rowid LIMIT 1",
            (time.time(),),
        ).fetchone()
        return (str(row[0]), str(row[1]), int(row[2])) if row else None
    finally:
        conn.close()


def _outbox_complete(delivery_id: str) -> None:
    conn = _outbox_connect()
    try:
        conn.execute("DELETE FROM scan_outbox WHERE delivery_id = ?", (delivery_id,))
        conn.commit()
    finally:
        conn.close()


def _outbox_fail(delivery_id: str, attempts: int) -> float:
    next_attempts = attempts + 1
    delay = min(60.0, float(2 ** min(next_attempts - 1, 6)))
    conn = _outbox_connect()
    try:
        conn.execute(
            "UPDATE scan_outbox SET attempts = ?, next_attempt = ? WHERE delivery_id = ?",
            (next_attempts, time.time() + delay, delivery_id),
        )
        conn.commit()
    finally:
        conn.close()
    return delay


def refresh_runtime_config() -> None:
    global _ack_queue
    data = _get_json(config_url())
    cfg = data.get("config") if isinstance(data, dict) else None
    if not isinstance(cfg, dict):
        return
    try:
        values = {
            "min_barcode_length": max(1, min(64, int(cfg.get("min_barcode_length", 4)))),
            "scan_queue_size": max(8, min(2048, int(cfg.get("scan_queue_size", 64)))),
            "scan_key_gap_seconds": max(0.05, min(5.0, float(cfg.get("scan_key_gap_seconds", 0.4)))),
        }
    except (TypeError, ValueError):
        return
    with _config_lock:
        changed = values != _runtime_config
        _runtime_config.update(values)
    if _ack_queue is not None:
        _ack_queue.maxsize = values["scan_queue_size"]
    if changed:
        log.info("Runtime scanner config updated: min_length=%d queue=%d key_gap=%.2fs", values["min_barcode_length"], values["scan_queue_size"], values["scan_key_gap_seconds"])


def runtime_scan_values(fallback_min: int, fallback_gap: float) -> tuple[int, float]:
    with _config_lock:
        return int(_runtime_config.get("min_barcode_length", fallback_min)), float(_runtime_config.get("scan_key_gap_seconds", fallback_gap))


def post_barcode(barcode: str, delivery_id: str) -> bool:
    return _post(
        scan_url(),
        {"barcode": barcode},
        log_scan=barcode,
        track_delivery=True,
        extra_headers={"X-B2M-Delivery-ID": delivery_id},
    )


def _enqueue_barcode(barcode: str) -> None:
    if _ack_queue is None:
        raise RuntimeError("scanner queues are not initialized")
    with _config_lock:
        capacity = int(_runtime_config.get("scan_queue_size", 64))
    try:
        delivery_id = _outbox_enqueue(barcode, capacity)
    except sqlite3.Error:
        log.exception("Could not persist scan to delivery outbox: %r", barcode)
        with _stats_lock:
            _stats["errors"] += 1
        return
    if not delivery_id:
        with _stats_lock:
            _stats["errors"] += 1
        log.error("Dropping scan because persistent delivery queue is full: %r", barcode)
        return

    with _stats_lock:
        _stats["scans"] += 1
    try:
        _ack_queue.put_nowait(barcode)
    except queue.Full:
        log.warning("Immediate acknowledgement queue full for scan=%r", barcode)
    pending = _outbox_count()
    log.info("scan=%r persisted delivery=%s pending=%d", barcode, delivery_id[:8], pending)
    _delivery_wakeup.set()


def ack_sender_loop() -> None:
    if _ack_queue is None:
        raise RuntimeError("ack queue is not initialized")
    while True:
        barcode = _ack_queue.get()
        try:
            _post(received_url(), {"barcode": barcode}, timeout_override=1.0, include_telemetry=False)
        finally:
            _ack_queue.task_done()


def scan_sender_loop() -> None:
    while True:
        try:
            row = _outbox_next()
        except sqlite3.Error:
            log.exception("Could not read persistent scanner outbox")
            _delivery_wakeup.wait(2.0)
            _delivery_wakeup.clear()
            continue
        if row is None:
            _delivery_wakeup.wait(1.0)
            _delivery_wakeup.clear()
            continue

        delivery_id, barcode, attempts = row
        if post_barcode(barcode, delivery_id):
            try:
                _outbox_complete(delivery_id)
            except sqlite3.Error:
                # The server has already confirmed this ID. Keeping it in the
                # outbox is safe because a later retry is idempotently replayed.
                log.exception("Could not remove completed delivery %s from outbox", delivery_id[:8])
            continue

        try:
            delay = _outbox_fail(delivery_id, attempts)
        except sqlite3.Error:
            log.exception("Could not update retry state for delivery %s", delivery_id[:8])
            delay = 2.0
        log.warning(
            "Delivery %s for scan=%r failed (attempt %d); retry in %.0fs",
            delivery_id[:8], barcode, attempts + 1, delay,
        )
        _delivery_wakeup.wait(delay)
        _delivery_wakeup.clear()


def heartbeat_loop(interval: float) -> None:
    while True:
        _post(heartbeat_url(), {})
        refresh_runtime_config()
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


def _read_device(device: InputDevice, layout: str, min_length: int, max_length: int, max_key_gap: float) -> None:
    buffer: list[str] = []
    shift_down = False
    altgr_down = False
    last_char_at = 0.0
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
        runtime_min, runtime_gap = runtime_scan_values(min_length, max_key_gap)
        if key_name in ENTER_KEYS:
            value = "".join(buffer).strip()
            buffer.clear(); last_char_at = 0.0
            if len(value) < runtime_min:
                if value:
                    log.warning("Ignoring too-short scan (%d < %d chars): %r", len(value), runtime_min, value)
                continue
            if len(value) > max_length:
                log.warning("Ignoring too-long scan (%d chars)", len(value))
                continue
            _enqueue_barcode(value)
            continue
        if key_name == "KEY_BACKSPACE":
            if buffer:
                buffer.pop()
            continue
        if key_name == "KEY_ESC":
            buffer.clear(); last_char_at = 0.0
            continue
        char = decode_key(key_name, shift_down, altgr_down, layout)
        if char is not None and len(buffer) < max_length:
            now = time.monotonic()
            if buffer and last_char_at and now - last_char_at > runtime_gap:
                log.warning("Discarding stale partial scan after %.0f ms gap: %r", (now - last_char_at) * 1000, "".join(buffer))
                buffer.clear()
            buffer.append(char); last_char_at = now
        elif char is None:
            log.debug("Unhandled HID key: %s", key_name)


def main() -> int:
    global _ack_queue
    device_spec = _env("SCANNER_DEVICE", "BARCODE_DEVICE", default="auto") or "auto"
    min_length = int(_env("MIN_BARCODE_LENGTH", default="4") or "4")
    max_length = int(_env("MAX_BARCODE_LENGTH", default="256") or "256")
    layout = (_env("SCANNER_KEYBOARD_LAYOUT", default="de") or "de").strip().lower()
    heartbeat_interval = float(_env("HEARTBEAT_INTERVAL", default="60") or "60")
    reconnect_interval = max(0.5, float(_env("SCANNER_RECONNECT_INTERVAL", default="2") or "2"))
    queue_size = max(8, int(_env("SCAN_QUEUE_SIZE", default="64") or "64"))
    max_key_gap = max(0.05, float(_env("SCAN_KEY_GAP_SECONDS", default="0.4") or "0.4"))
    if layout not in {"de", "us"}:
        raise RuntimeError("SCANNER_KEYBOARD_LAYOUT must be 'de' or 'us'")
    api_token()
    _runtime["layout"] = layout
    _runtime["device"] = "disconnected"
    with _config_lock:
        _runtime_config.update({"min_barcode_length": min_length, "scan_queue_size": queue_size, "scan_key_gap_seconds": max_key_gap})

    _init_outbox()
    _ack_queue = queue.Queue(maxsize=queue_size)
    refresh_runtime_config()
    with _config_lock:
        queue_size = int(_runtime_config["scan_queue_size"])
        min_length = int(_runtime_config["min_barcode_length"])
        max_key_gap = float(_runtime_config["scan_key_gap_seconds"])

    pending = _outbox_count()
    log.info(
        "Scanner bridge v%s starting, device=%s, layout=%s, min_length=%d, queue=%d, key_gap=%.2fs, outbox=%s, recovered=%d, posting to %s",
        SCANNER_VERSION, device_spec, layout, min_length, queue_size, max_key_gap, _outbox_path, pending, scan_url(),
    )
    threading.Thread(target=ack_sender_loop, daemon=True, name="scan-ack").start()
    threading.Thread(target=scan_sender_loop, daemon=True, name="scan-sender").start()
    if pending:
        _delivery_wakeup.set()
    if heartbeat_interval > 0:
        threading.Thread(target=heartbeat_loop, args=(max(15.0, heartbeat_interval),), daemon=True, name="heartbeat").start()

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
            log.info("Scanner connected on %s (%s), layout=%s", device_path, device.name, layout)
            _read_device(device, layout, min_length, max_length, max_key_gap)
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
