from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import SystemState
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
