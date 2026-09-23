from __future__ import annotations

import io
import json
import os
from pathlib import Path
import queue
import tempfile
import threading
import uuid
from datetime import datetime, timezone

import barcode as barcode_lib
import segno
from barcode.writer import SVGWriter
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.auth import require_token
from app.database import SessionLocal, get_db
from app.models import ApiToken, SystemState
from app.services.niimblue import print_image_base64, printer_status
from app.templating import set_cached_theme
from app.theme import THEME_DEFAULTS, build_theme_css, get_theme, save_theme

router = APIRouter()

_SCANNER_KEYS = {
    "min_barcode_length": ("scanner.min_barcode_length", 4, 1, 64, int),
    "scan_queue_size": ("scanner.scan_queue_size", 64, 8, 2048, int),
    "scan_key_gap_seconds": ("scanner.scan_key_gap_seconds", 0.4, 0.05, 5.0, float),
}

_JOB_LOCK = threading.Lock()
_WORKER_LOCK = threading.Lock()
_JOBS: dict[str, dict] = {}
_JOB_QUEUE: queue.Queue[str] = queue.Queue(maxsize=8)
_WORKER_STARTED = False
_MAX_JOB_HISTORY = 40
_MAX_JOB_BASE64_CHARS = 24_000_000
_MAX_PAGE_BASE64_CHARS = 8_000_000
_SPOOL_DIR = Path(tempfile.gettempdir()) / "b2m-print-jobs"
_STATS_KEYS = {
    "jobs": "labels.b21.stats.jobs",
    "labels": "labels.b21.stats.labels",
    "failed": "labels.b21.stats.failed",
    "last_print_at": "labels.b21.stats.last_print_at",
    "last_error": "labels.b21.stats.last_error",
}


def _state_value(db: Session, key: str, default: str = "") -> str:
    row = db.get(SystemState, key)
    return row.value if row and row.value is not None else default


def _set_state(db: Session, key: str, value: str) -> None:
    row = db.get(SystemState, key)
    if row:
        row.value = value
    else:
        db.add(SystemState(key=key, value=value))


def _scanner_config(db: Session) -> dict:
    result = {}
    for field, (key, default, minimum, maximum, cast) in _SCANNER_KEYS.items():
        raw = _state_value(db, key, str(default))
        try:
            value = cast(raw)
        except (TypeError, ValueError):
            value = default
        result[field] = max(minimum, min(maximum, value))
    return result


def _require_admin(request: Request):
    if not request.session.get("is_admin", False):
        return JSONResponse({"error": "admin required"}, status_code=403)
    return None


# This router is registered before the legacy labels router. Keeping the endpoint
# path identical fixes all existing previews without a JS migration. segno.make_qr
# explicitly disables Micro-QR, which is much less reliably scanned on tiny labels.
@router.get("/labels/code.svg")
def stable_code_svg(
    value: str = Query(..., min_length=1, max_length=256),
    kind: str = Query("auto"),
):
    kind = kind.lower().strip()
    if kind == "auto":
        try:
            value.encode("ascii")
            kind = "code128" if len(value) <= 32 else "qr"
        except UnicodeEncodeError:
            kind = "qr"
    try:
        if kind == "qr":
            qr = segno.make_qr(value, error="m")
            buf = io.BytesIO()
            qr.save(buf, kind="svg", scale=4, border=2, xmldecl=False)
            content = buf.getvalue()
        else:
            raw = value.strip()
            if kind == "code128":
                raw.encode("ascii")
                cls = barcode_lib.get_barcode_class("code128")
                code_value = raw
            elif kind == "ean13":
                if not raw.isdigit() or len(raw) not in (12, 13):
                    raise ValueError("EAN-13 only works with 12 or 13 digits")
                cls = barcode_lib.get_barcode_class("ean13")
                code_value = raw[:12]
            elif kind == "upca":
                if not raw.isdigit() or len(raw) not in (11, 12):
                    raise ValueError("UPC-A only works with 11 or 12 digits")
                cls = barcode_lib.get_barcode_class("upca")
                code_value = raw[:11]
            else:
                raise ValueError("Unsupported symbology")
            buf = io.BytesIO()
            cls(code_value, writer=SVGWriter()).write(buf, options={
                "write_text": False,
                "quiet_zone": 2.0,
                "module_height": 12.0,
                "font_size": 0,
            })
            content = buf.getvalue()
    except (UnicodeEncodeError, ValueError, barcode_lib.errors.BarcodeError) as exc:
        return Response(content=str(exc), status_code=422, media_type="text/plain")
    return Response(content=content, media_type="image/svg+xml", headers={"X-Code-Kind": kind})


@router.get("/scanner/config")
def scanner_runtime_config(
    token: ApiToken = Depends(require_token),
    db: Session = Depends(get_db),
):
    return {"ok": True, "config": _scanner_config(db)}


@router.get("/api/settings/scanner-bridge")
def scanner_bridge_settings(request: Request, db: Session = Depends(get_db)):
    if denied := _require_admin(request):
        return denied
    return {"config": _scanner_config(db)}


@router.post("/api/settings/scanner-bridge")
async def save_scanner_bridge_settings(request: Request, db: Session = Depends(get_db)):
    if denied := _require_admin(request):
        return denied
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)
    current = _scanner_config(db)
    for field, (key, default, minimum, maximum, cast) in _SCANNER_KEYS.items():
        if field not in body:
            continue
        try:
            value = cast(body[field])
        except (TypeError, ValueError):
            return JSONResponse({"error": f"Invalid value for {field}"}, status_code=400)
        if not minimum <= value <= maximum:
            return JSONResponse({"error": f"{field} must be between {minimum} and {maximum}"}, status_code=400)
        current[field] = value
        _set_state(db, key, f"{value:g}" if isinstance(value, float) else str(value))
    db.commit()
    return {"ok": True, "config": current}


@router.post("/api/theme/preview")
async def theme_preview(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        return Response("", media_type="text/css")
    values = dict(THEME_DEFAULTS)
    for key in values:
        if key in body:
            values[key] = str(body[key]).lower() if key == "epaper" else str(body[key])
    return Response(build_theme_css(values), media_type="text/css", headers={"Cache-Control": "no-store"})


@router.post("/api/theme/accessibility")
async def save_theme_accessibility(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    values = {
        "epaper": "true" if bool(body.get("epaper")) else "false",
        "contrast": str(body.get("contrast", THEME_DEFAULTS["contrast"])),
    }
    save_theme(db, values)
    set_cached_theme(get_theme(db))
    return {"ok": True, **values}


@router.post("/api/theme/preferences")
async def save_theme_preferences(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    values = {}
    if "date_style" in body:
        values["date_style"] = str(body["date_style"])
    if values:
        save_theme(db, values)
        set_cached_theme(get_theme(db))
    return {"ok": True, "theme": get_theme(db)}


def _job_copy(job: dict) -> dict:
    return {key: value for key, value in job.items() if key != "spool_path"}


def _record_print_stats(*, labels: int = 0, failed: bool = False, error: str = "") -> None:
    db = SessionLocal()
    try:
        def inc(name: str, amount: int = 1):
            key = _STATS_KEYS[name]
            try:
                value = int(_state_value(db, key, "0"))
            except ValueError:
                value = 0
            _set_state(db, key, str(value + amount))

        inc("jobs")
        if labels:
            inc("labels", labels)
        if failed:
            inc("failed")
        _set_state(db, _STATS_KEYS["last_print_at"], datetime.now(timezone.utc).isoformat())
        _set_state(db, _STATS_KEYS["last_error"], error[:1000] if failed else "")
        db.commit()
    finally:
        db.close()


def _remove_spool(path: str | None) -> None:
    if not path:
        return
    try:
        os.unlink(path)
    except OSError:
        pass


def _trim_job_history_locked() -> None:
    terminal = sorted(
        (row for row in _JOBS.values() if row.get("status") in {"completed", "failed"}),
        key=lambda row: row.get("finished_at") or row.get("created_at") or "",
    )
    while len(terminal) > _MAX_JOB_HISTORY:
        row = terminal.pop(0)
        _JOBS.pop(row["id"], None)


def _write_spool(job_id: str, pages: list[dict]) -> str:
    _SPOOL_DIR.mkdir(parents=True, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix=f"{job_id}-", suffix=".json", dir=str(_SPOOL_DIR))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(pages, handle, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        _remove_spool(path)
        raise
    return path


def _load_spool(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as handle:
        pages = json.load(handle)
    if not isinstance(pages, list):
        raise RuntimeError("Invalid print job spool")
    return pages


def _run_print_job(job_id: str) -> None:
    with _JOB_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        spool_path = job.get("spool_path")
        job["status"] = "running"
        job["started_at"] = datetime.now(timezone.utc).isoformat()

    printed = 0
    error = ""
    pages: list[dict] = []
    try:
        pages = _load_spool(str(spool_path))
        _remove_spool(str(spool_path))
        with _JOB_LOCK:
            if job_id in _JOBS:
                _JOBS[job_id]["spool_path"] = None

        for index, page in enumerate(pages):
            quantity = max(1, min(int(page.get("quantity") or 1), 99))
            print_image_base64(
                str(page["image_base64"]),
                width_mm=float(page["width_mm"]),
                height_mm=float(page["height_mm"]),
                quantity=quantity,
                density=int(page.get("density") or 3),
                label_type=int(page.get("label_type") or 1),
                dpi=int(page.get("dpi") or 300),
                threshold=int(page.get("threshold") or 128),
            )
            printed += quantity
            # Drop the largest object as soon as this page has left the process.
            page["image_base64"] = ""
            with _JOB_LOCK:
                if job_id in _JOBS:
                    _JOBS[job_id]["completed_pages"] = index + 1
                    _JOBS[job_id]["printed_labels"] = printed
    except Exception as exc:
        error = str(exc)
    finally:
        _remove_spool(str(spool_path) if spool_path else None)
        pages.clear()

    with _JOB_LOCK:
        job = _JOBS.get(job_id)
        if job:
            job["status"] = "failed" if error else "completed"
            job["error"] = error
            job["printed_labels"] = printed
            job["finished_at"] = datetime.now(timezone.utc).isoformat()
            job["spool_path"] = None
        _trim_job_history_locked()
    _record_print_stats(labels=printed, failed=bool(error), error=error)


def _printer_worker() -> None:
    while True:
        job_id = _JOB_QUEUE.get()
        try:
            _run_print_job(job_id)
        finally:
            _JOB_QUEUE.task_done()


def _ensure_print_worker() -> None:
    global _WORKER_STARTED
    if _WORKER_STARTED:
        return
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return
        _SPOOL_DIR.mkdir(parents=True, exist_ok=True)
        # Spool files cannot be resumed after a process restart because the
        # corresponding in-memory job metadata is gone. Remove leftovers now.
        for path in _SPOOL_DIR.glob("*.json"):
            _remove_spool(str(path))
        threading.Thread(target=_printer_worker, daemon=True, name="b2m-printer").start()
        _WORKER_STARTED = True


@router.post("/labels/b21/jobs")
async def create_print_job(request: Request):
    body = await request.json()
    pages = body.get("pages") if isinstance(body, dict) else None
    if not isinstance(pages, list) or not pages:
        return JSONResponse({"error": "pages array is required"}, status_code=400)
    if len(pages) > 100:
        return JSONResponse({"error": "A print job may contain at most 100 entries"}, status_code=400)
    status = printer_status()
    if not status.get("configured"):
        return JSONResponse({"error": "NIIMBOT printing is not configured"}, status_code=400)
    if not status.get("connected"):
        return JSONResponse({"error": "B21 Pro is not connected"}, status_code=409)

    clean_pages = []
    total_chars = 0
    for page in pages:
        if not isinstance(page, dict) or not page.get("image_base64"):
            return JSONResponse({"error": "Every page needs image_base64"}, status_code=400)
        image_base64 = str(page["image_base64"])
        if image_base64.startswith("data:") and "," in image_base64:
            image_base64 = image_base64.split(",", 1)[1]
        if len(image_base64) > _MAX_PAGE_BASE64_CHARS:
            return JSONResponse({"error": "A rendered label image is too large"}, status_code=413)
        total_chars += len(image_base64)
        if total_chars > _MAX_JOB_BASE64_CHARS:
            return JSONResponse({"error": "Print job image data is too large"}, status_code=413)
        clean_pages.append({
            "image_base64": image_base64,
            "width_mm": float(page.get("width_mm") or 0),
            "height_mm": float(page.get("height_mm") or 0),
            "quantity": max(1, min(int(page.get("quantity") or 1), 99)),
            "density": max(1, min(int(page.get("density") or 3), 5)),
            "label_type": max(1, int(page.get("label_type") or 1)),
            "dpi": max(100, min(int(page.get("dpi") or 300), 1200)),
            "threshold": max(1, min(int(page.get("threshold") or 128), 255)),
        })
        if clean_pages[-1]["width_mm"] <= 0 or clean_pages[-1]["height_mm"] <= 0:
            return JSONResponse({"error": "Invalid label dimensions"}, status_code=400)

    _ensure_print_worker()
    if _JOB_QUEUE.full():
        return JSONResponse({"error": "Printer queue is full; wait for an active job to finish"}, status_code=429)

    job_id = uuid.uuid4().hex[:16]
    try:
        spool_path = _write_spool(job_id, clean_pages)
    except OSError as exc:
        return JSONResponse({"error": f"Could not spool print job: {exc}"}, status_code=507)
    clean_pages.clear()

    now = datetime.now(timezone.utc).isoformat()
    job = {
        "id": job_id,
        "status": "queued",
        "created_at": now,
        "started_at": None,
        "finished_at": None,
        "completed_pages": 0,
        "page_count": len(pages),
        "printed_labels": 0,
        "error": "",
        "spool_path": spool_path,
    }
    with _JOB_LOCK:
        _JOBS[job_id] = job
        _trim_job_history_locked()
    try:
        _JOB_QUEUE.put_nowait(job_id)
    except queue.Full:
        with _JOB_LOCK:
            _JOBS.pop(job_id, None)
        _remove_spool(spool_path)
        return JSONResponse({"error": "Printer queue is full; wait for an active job to finish"}, status_code=429)
    return JSONResponse(_job_copy(job), status_code=202)


@router.get("/labels/b21/jobs/{job_id}")
def print_job_status(job_id: str):
    with _JOB_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return JSONResponse({"error": "Print job not found"}, status_code=404)
        return _job_copy(job)


@router.get("/labels/b21/stats")
def printer_stats(db: Session = Depends(get_db)):
    def intval(name: str) -> int:
        try:
            return int(_state_value(db, _STATS_KEYS[name], "0"))
        except ValueError:
            return 0

    with _JOB_LOCK:
        active = sum(1 for row in _JOBS.values() if row["status"] in {"queued", "running"})
    return {
        "jobs": intval("jobs"),
        "labels": intval("labels"),
        "failed": intval("failed"),
        "active_jobs": active,
        "queue_capacity": _JOB_QUEUE.maxsize,
        "queue_depth": _JOB_QUEUE.qsize(),
        "last_print_at": _state_value(db, _STATS_KEYS["last_print_at"], "") or None,
        "last_error": _state_value(db, _STATS_KEYS["last_error"], "") or None,
        "status": printer_status(),
    }
