from __future__ import annotations

import json
import math
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import SystemState
from app.services import niimblue
from app.services.niimblue import _connected as niim_connected
from app.services.niimblue import config as niim_config
from app.services.niimblue import is_configured as niim_is_configured
from app.services.niimblue_batch_v30 import print_images_base64
from app.services.shopping import get_default_shopping_list_id, get_shopping_lists
from app.services.shopping_print import (
    LABEL_TYPES,
    load_print_settings,
    save_category_aliases,
    save_category_order,
    save_local_content,
    shopping_list_payload,
)
from app.services.shopping_print_overrides import (
    _ITEM_OVERRIDES_KEY,
    apply_item_overrides,
    load_item_overrides,
    load_marker_style,
    save_item_override,
)

router = APIRouter()

_TOP_MARGIN_KEY = "shopping_print.top_margin_mm"
_TOP_MARGIN_DEFAULT = 2.2

_PRINT_JOB_LOCK = threading.Lock()
_PRINT_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="b2m-label-print")
_PRINT_JOBS: dict[str, dict] = {}


def _valid_list_id(list_id: str) -> bool:
    available = {str(row.get("id")) for row in get_shopping_lists(force=False)}
    return bool(list_id and list_id in available)


def _load_top_margin(db: Session) -> float:
    row = db.get(SystemState, _TOP_MARGIN_KEY)
    if not row or row.value is None:
        return _TOP_MARGIN_DEFAULT
    try:
        value = float(row.value)
    except (TypeError, ValueError):
        return _TOP_MARGIN_DEFAULT
    return round(max(0.0, min(20.0, value)), 1)


def _save_all_item_overrides(db: Session, value: dict) -> None:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    row = db.get(SystemState, _ITEM_OVERRIDES_KEY)
    if row:
        row.value = encoded
    else:
        db.add(SystemState(key=_ITEM_OVERRIDES_KEY, value=encoded))
    db.commit()


@router.get("/api/shopping-print/bootstrap-v31")
def shopping_print_bootstrap_v31(db: Session = Depends(get_db)):
    """Fast Shopping Print startup data without expensive printer diagnostics.

    The legacy bootstrap called printer_status(), which can perform /connected,
    /info and RFID requests before returning the Mealie list selector. Shopping
    Print only needs a connection boolean at startup, so bound that check to
    800 ms and defer detailed printer diagnostics to the printer-specific APIs.
    """
    lists = get_shopping_lists(force=False)
    print_settings = load_print_settings(db)
    print_settings["top_margin_mm"] = _load_top_margin(db)
    print_settings["item_marker_style"] = load_marker_style(db)

    cfg = niim_config()
    configured = bool(cfg["url"] and cfg["address"] and cfg["transport"] in {"ble", "serial"})
    connected = niim_connected(timeout=0.8) if configured else False
    printer = {
        "configured": configured,
        "connected": connected,
        "address": cfg["address"],
        "transport": cfg["transport"],
        "print_task": cfg["print_task"],
        "dpi": cfg["dpi"],
        "max_label_width_mm": cfg["max_label_width_mm"],
        "status_mode": "fast",
    }
    return {
        "lists": lists,
        "default_list_id": get_default_shopping_list_id(db),
        "settings": print_settings,
        "printer": printer,
        "poll_interval_seconds": settings.shopping_print_poll_interval_seconds,
        "label_types": [{"value": value, "name": name} for value, name in LABEL_TYPES.items()],
    }


def _normalize_print_groups(body: dict) -> tuple[list[dict], int]:
    pages = body.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("pages array required")
    if len(pages) > 100:
        raise ValueError("At most 100 label pages can be printed in one queue")

    defaults = {
        "width_mm": body.get("width_mm"),
        "height_mm": body.get("height_mm"),
        "density": body.get("density"),
        "label_type": body.get("label_type"),
        "dpi": body.get("dpi"),
        "threshold": body.get("threshold"),
    }
    groups: list[dict] = []
    total_labels = 0
    for page in pages:
        if not isinstance(page, dict):
            raise ValueError("Invalid label page")
        settings_for_page = {}
        for name in ("width_mm", "height_mm", "density", "label_type", "dpi", "threshold"):
            raw = page.get(name, defaults[name])
            if raw is None:
                if name in {"density", "label_type", "dpi", "threshold"}:
                    raw = {"density": 3, "label_type": 1, "dpi": 300, "threshold": 128}[name]
                else:
                    raise ValueError("Every page requires label width and height")
            try:
                value = float(raw) if name in {"width_mm", "height_mm"} else int(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid {name} for label page") from exc
            if not math.isfinite(value):
                raise ValueError(f"Invalid {name} for label page")
            settings_for_page[name] = value

        image = str(page.get("image_base64") or page.get("imageBase64") or "")
        if image.startswith("data:") and "," in image:
            image = image.split(",", 1)[1]
        if not image:
            raise ValueError("Every label page requires a rendered image")
        try:
            quantity = max(1, min(int(page.get("quantity") or 1), 99))
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid quantity for label page") from exc
        total_labels += quantity
        key = tuple(settings_for_page[name] for name in ("width_mm", "height_mm", "density", "label_type", "dpi", "threshold"))
        if groups and groups[-1]["key"] == key:
            groups[-1]["pages"].append({"image_base64": image, "quantity": quantity})
            groups[-1]["page_count"] += 1
        else:
            groups.append({"key": key, "settings": settings_for_page, "pages": [{"image_base64": image, "quantity": quantity}], "page_count": 1})
    return groups, total_labels


def _public_print_job(job: dict) -> dict:
    return {
        key: job.get(key)
        for key in ("id", "status", "page_count", "completed_pages", "printed_labels", "total_labels", "error")
    }


def _run_print_job(job_id: str, groups: list[dict]) -> None:
    with _PRINT_JOB_LOCK:
        job = _PRINT_JOBS.get(job_id)
        if not job:
            return
        job["status"] = "printing"

    for group in groups:
        options = group["settings"]
        try:
            result = print_images_base64(
                group["pages"],
                width_mm=options["width_mm"],
                height_mm=options["height_mm"],
                density=options["density"],
                label_type=options["label_type"],
                dpi=options["dpi"],
                threshold=options["threshold"],
            )
        except niimblue.PrintOutcomeUnknown as exc:
            with _PRINT_JOB_LOCK:
                job = _PRINT_JOBS[job_id]
                job.update(status="unknown", error=str(exc), finished=True)
            return
        except Exception as exc:
            with _PRINT_JOB_LOCK:
                job = _PRINT_JOBS[job_id]
                job.update(status="failed", error=str(exc), finished=True)
            return
        with _PRINT_JOB_LOCK:
            job = _PRINT_JOBS[job_id]
            job["completed_pages"] += group["page_count"]
            job["printed_labels"] += int(result.get("quantity") or 0)

    with _PRINT_JOB_LOCK:
        job = _PRINT_JOBS[job_id]
        job.update(status="completed", finished=True)


@router.post("/labels/b21/jobs", status_code=202)
def b21_create_print_job(body: dict):
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)
    if not niim_is_configured():
        return JSONResponse({"error": "NIIMBOT printing is not configured"}, status_code=400)
    try:
        groups, total_labels = _normalize_print_groups(body)
    except (TypeError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    job_id = uuid.uuid4().hex
    page_count = sum(group["page_count"] for group in groups)
    job = {
        "id": job_id,
        "status": "queued",
        "page_count": page_count,
        "completed_pages": 0,
        "printed_labels": 0,
        "total_labels": total_labels,
        "error": None,
        "finished": False,
    }
    with _PRINT_JOB_LOCK:
        # Keep the in-memory status table bounded; active jobs are never removed.
        if len(_PRINT_JOBS) >= 100:
            for old_id, old_job in list(_PRINT_JOBS.items()):
                if old_job.get("finished"):
                    _PRINT_JOBS.pop(old_id, None)
                    if len(_PRINT_JOBS) < 90:
                        break
        if len(_PRINT_JOBS) >= 100:
            return JSONResponse({"error": "Printer queue is full; try again shortly"}, status_code=503)
        _PRINT_JOBS[job_id] = job
    try:
        _PRINT_EXECUTOR.submit(_run_print_job, job_id, groups)
    except RuntimeError as exc:
        with _PRINT_JOB_LOCK:
            _PRINT_JOBS.pop(job_id, None)
        return JSONResponse({"error": str(exc)}, status_code=503)
    return _public_print_job(job)


@router.get("/labels/b21/jobs/{job_id}")
def b21_get_print_job(job_id: str):
    with _PRINT_JOB_LOCK:
        job = _PRINT_JOBS.get(job_id)
        if not job:
            return JSONResponse({"error": "Print job not found"}, status_code=404)
        return _public_print_job(job)


@router.post("/labels/b21/print-batch-v30")
def b21_print_batch_v30(body: dict):
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)
    if not niim_is_configured():
        return JSONResponse({"error": "NIIMBOT printing is not configured"}, status_code=400)

    pages = body.get("pages")
    if not isinstance(pages, list) or not pages:
        return JSONResponse({"error": "pages array required"}, status_code=400)
    try:
        result = print_images_base64(
            pages,
            width_mm=float(body.get("width_mm")),
            height_mm=float(body.get("height_mm")),
            density=int(body.get("density") or 3),
            label_type=int(body.get("label_type") or 1),
            dpi=int(body.get("dpi") or 300),
            threshold=int(body.get("threshold") or 128),
        )
        return result
    except (TypeError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.post("/api/shopping-print/item-overrides-v30")
def shopping_print_item_override_v30(body: dict, db: Session = Depends(get_db)):
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)
    list_id = str(body.get("list_id") or "").strip()
    if not _valid_list_id(list_id):
        return JSONResponse({"error": "Shopping list not found"}, status_code=404)
    try:
        saved = save_item_override(
            db,
            list_id,
            str(body.get("key") or ""),
            str(body.get("name_alias") or ""),
            str(body.get("quantity_alias") or ""),
            str(body.get("unit_alias") or ""),
            str(body.get("source_name") or ""),
            str(body.get("source_quantity_text") or ""),
            str(body.get("source_unit_text") or ""),
            bool(body.get("hide_unit", False)),
            bool(body.get("hide_quantity", False)),
        )
        payload = apply_item_overrides(db, list_id, shopping_list_payload(db, list_id))
        return {"ok": True, "saved": saved, "item_overrides": payload.get("item_overrides", [])}
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.post("/api/shopping-print/reset-list-v30")
def shopping_print_reset_list_v30(body: dict, db: Session = Depends(get_db)):
    """Reset list-specific print customizations without touching print settings."""
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)
    list_id = str(body.get("list_id") or "").strip()
    if not _valid_list_id(list_id):
        return JSONResponse({"error": "Shopping list not found"}, status_code=404)
    try:
        save_category_order(db, list_id, [])
        save_category_aliases(db, list_id, {})
        save_local_content(db, list_id, "", [])
        overrides = load_item_overrides(db)
        overrides.pop(list_id, None)
        _save_all_item_overrides(db, overrides)
        payload = apply_item_overrides(db, list_id, shopping_list_payload(db, list_id))
        return {
            "ok": True,
            "list_id": list_id,
            "category_order": payload.get("category_order", []),
            "category_aliases": payload.get("category_aliases", {}),
            "local_comment": payload.get("local_comment", ""),
            "local_entries": payload.get("local_entries", []),
            "item_overrides": payload.get("item_overrides", []),
        }
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
