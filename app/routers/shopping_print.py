from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import SystemState
from app.services.niimblue import is_configured as niim_is_configured, print_image_base64, printer_status
from app.services.shopping import get_default_shopping_list_id, get_shopping_lists
from app.services.shopping_print import (
    LABEL_TYPES,
    load_category_aliases,
    load_local_content,
    load_print_settings,
    ordered_categories,
    save_category_aliases,
    save_category_order,
    save_local_content,
    save_print_settings,
    shopping_list_payload,
)
from app.services.shopping_print_overrides import (
    apply_item_overrides,
    delete_item_override,
    load_marker_style,
    save_item_override,
    save_marker_style,
)
from app.templating import templates

router = APIRouter()

_TOP_MARGIN_KEY = "shopping_print.top_margin_mm"
_TOP_MARGIN_DEFAULT = 2.2


def _load_top_margin(db: Session) -> float:
    row = db.get(SystemState, _TOP_MARGIN_KEY)
    if not row or row.value is None:
        return _TOP_MARGIN_DEFAULT
    try:
        value = float(row.value)
    except (TypeError, ValueError):
        return _TOP_MARGIN_DEFAULT
    return round(max(0.0, min(20.0, value)), 1)


def _save_top_margin(db: Session, value) -> float:
    try:
        clean = round(float(value), 1)
    except (TypeError, ValueError) as exc:
        raise ValueError("top_margin_mm must be a number") from exc
    if not 0 <= clean <= 20:
        raise ValueError("top_margin_mm must be between 0 and 20")
    row = db.get(SystemState, _TOP_MARGIN_KEY)
    if row:
        row.value = str(clean)
    else:
        db.add(SystemState(key=_TOP_MARGIN_KEY, value=str(clean)))
    db.commit()
    return clean


def _valid_list_id(list_id: str) -> bool:
    available = {str(row.get("id")) for row in get_shopping_lists(force=False)}
    return bool(list_id and list_id in available)


def _category_text(value) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_payload_categories(db: Session, list_id: str, payload: dict) -> dict:
    """Collapse local category aliases/case variants onto one canonical section."""
    canonical: dict[str, str] = {}
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        name = _category_text(item.get("category") or "Other") or "Other"
        canonical.setdefault(name.casefold(), name)
        item["category"] = canonical[name.casefold()]

    aliases = load_category_aliases(db).get(str(list_id), {})
    alias_to_source: dict[str, str] = {}
    for source, alias in aliases.items():
        source_name = _category_text(source)
        alias_name = _category_text(alias)
        if source_name:
            canonical.setdefault(source_name.casefold(), source_name)
            if alias_name:
                alias_to_source[alias_name.casefold()] = canonical[source_name.casefold()]

    for entry in payload.get("local_entries") or []:
        if not isinstance(entry, dict):
            continue
        name = _category_text(entry.get("category") or "Extra") or "Extra"
        key = name.casefold()
        if key in alias_to_source:
            name = alias_to_source[key]
            key = name.casefold()
        if key in canonical:
            name = canonical[key]
        else:
            canonical[key] = name
        entry["category"] = name

    categories: list[str] = []
    seen: set[str] = set()
    for item in payload.get("items") or []:
        name = _category_text(item.get("category") or "Other") or "Other"
        key = name.casefold()
        if key not in seen:
            categories.append(name)
            seen.add(key)
    for entry in payload.get("local_entries") or []:
        name = _category_text(entry.get("category") or "Extra") or "Extra"
        key = name.casefold()
        if key not in seen:
            categories.append(name)
            seen.add(key)
    payload["categories"] = sorted(categories, key=str.casefold)
    payload["category_order"] = ordered_categories(payload["categories"], payload.get("category_order") or [])
    return payload


def _canonicalize_local_entries(db: Session, list_id: str, entries) -> list:
    payload = _normalize_payload_categories(db, list_id, shopping_list_payload(db, list_id))
    canonical = {str(name).casefold(): str(name) for name in payload.get("categories") or []}
    aliases = load_category_aliases(db).get(str(list_id), {})
    for source, alias in aliases.items():
        source_name = _category_text(source)
        alias_name = _category_text(alias)
        if source_name:
            canonical.setdefault(source_name.casefold(), source_name)
            if alias_name:
                canonical[alias_name.casefold()] = canonical[source_name.casefold()]

    result = []
    for row in entries or []:
        if not isinstance(row, dict):
            continue
        clean = dict(row)
        category = _category_text(clean.get("category") or "Extra") or "Extra"
        clean["category"] = canonical.get(category.casefold(), category)
        result.append(clean)
    return result


def _full_payload(db: Session, list_id: str) -> dict:
    payload = shopping_list_payload(db, list_id)
    payload = _normalize_payload_categories(db, list_id, payload)
    return apply_item_overrides(db, list_id, payload)


def _prune_category_state(db: Session, list_id: str, payload: dict) -> None:
    available = {str(name).casefold(): str(name) for name in payload.get("categories") or [] if str(name).strip()}
    clean_order = []
    seen = set()
    for name in payload.get("category_order") or []:
        key = str(name).casefold()
        actual = available.get(key)
        if actual and key not in seen:
            clean_order.append(actual)
            seen.add(key)
    save_category_order(db, list_id, clean_order)

    aliases = load_category_aliases(db).get(str(list_id), {})
    clean_aliases = {
        source: alias
        for source, alias in aliases.items()
        if str(source).casefold() in available
    }
    save_category_aliases(db, list_id, clean_aliases)


def _saved_local_response(db: Session, list_id: str, saved: dict) -> dict:
    payload = _full_payload(db, list_id)
    _prune_category_state(db, list_id, payload)
    payload = _full_payload(db, list_id)
    return {
        "ok": True,
        "list_id": list_id,
        **saved,
        "category_order": payload.get("category_order", []),
        "category_aliases": payload.get("category_aliases", {}),
        "categories": payload.get("categories", []),
    }


@router.get("/shopping-print", response_class=HTMLResponse)
def shopping_print_page(request: Request):
    return templates.TemplateResponse(request, "shopping_print.html", {})


@router.get("/api/shopping-print/bootstrap")
def shopping_print_bootstrap(db: Session = Depends(get_db)):
    lists = get_shopping_lists(force=False)
    try:
        status = printer_status()
    except Exception as exc:
        status = {"configured": niim_is_configured(), "connected": False, "error": str(exc)}
    print_settings = load_print_settings(db)
    print_settings["top_margin_mm"] = _load_top_margin(db)
    print_settings["item_marker_style"] = load_marker_style(db)
    return {
        "lists": lists,
        "default_list_id": get_default_shopping_list_id(db),
        "settings": print_settings,
        "printer": status,
        "poll_interval_seconds": settings.shopping_print_poll_interval_seconds,
        "label_types": [{"value": value, "name": name} for value, name in LABEL_TYPES.items()],
    }


@router.get("/api/shopping-print/lists/{list_id}")
def shopping_print_list(list_id: str, db: Session = Depends(get_db)):
    try:
        return _full_payload(db, list_id)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.post("/api/shopping-print/settings")
def shopping_print_save_settings(body: dict, db: Session = Depends(get_db)):
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)
    try:
        saved = save_print_settings(db, body)
        saved["top_margin_mm"] = _save_top_margin(db, body.get("top_margin_mm", _load_top_margin(db)))
        marker_style = save_marker_style(db, body.get("item_marker_style", load_marker_style(db)))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    saved["item_marker_style"] = marker_style
    return {"ok": True, "settings": saved}


@router.post("/api/shopping-print/category-order")
def shopping_print_save_category_order(body: dict, db: Session = Depends(get_db)):
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)
    list_id = str(body.get("list_id") or "").strip()
    order = body.get("category_order")
    aliases = body.get("category_aliases", {})
    if not isinstance(order, list):
        return JSONResponse({"error": "category_order array required"}, status_code=400)
    if not isinstance(aliases, dict):
        return JSONResponse({"error": "category_aliases object required"}, status_code=400)
    if not _valid_list_id(list_id):
        return JSONResponse({"error": "Shopping list not found"}, status_code=404)
    try:
        saved_order = save_category_order(db, list_id, order)
        saved_aliases = save_category_aliases(db, list_id, aliases)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {
        "ok": True,
        "list_id": list_id,
        "category_order": saved_order,
        "category_aliases": saved_aliases,
    }


@router.post("/api/shopping-print/local-content")
def shopping_print_save_local_content(body: dict, db: Session = Depends(get_db)):
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)
    list_id = str(body.get("list_id") or "").strip()
    if not _valid_list_id(list_id):
        return JSONResponse({"error": "Shopping list not found"}, status_code=404)
    try:
        saved = save_local_content(
            db,
            list_id,
            str(body.get("comment") or ""),
            _canonicalize_local_entries(db, list_id, body.get("entries") or []),
        )
        return _saved_local_response(db, list_id, saved)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.post("/api/shopping-print/local-content/add")
def shopping_print_add_local_entry(body: dict, db: Session = Depends(get_db)):
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)
    list_id = str(body.get("list_id") or "").strip()
    if not _valid_list_id(list_id):
        return JSONResponse({"error": "Shopping list not found"}, status_code=404)
    current = load_local_content(db).get(list_id, {"comment": "", "entries": []})
    entries = [dict(row) for row in current.get("entries") or []]
    entries.append({
        "name": str(body.get("name") or ""),
        "quantity_text": str(body.get("quantity_text") or ""),
        "category": str(body.get("category") or "Extra"),
    })
    try:
        saved = save_local_content(
            db,
            list_id,
            current.get("comment") or "",
            _canonicalize_local_entries(db, list_id, entries),
        )
        return _saved_local_response(db, list_id, saved)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.post("/api/shopping-print/local-content/delete")
def shopping_print_delete_local_entry(body: dict, db: Session = Depends(get_db)):
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)
    list_id = str(body.get("list_id") or "").strip()
    entry_id = str(body.get("entry_id") or "").strip()
    if not _valid_list_id(list_id):
        return JSONResponse({"error": "Shopping list not found"}, status_code=404)
    if not entry_id:
        return JSONResponse({"error": "entry_id is required"}, status_code=400)
    current = load_local_content(db).get(list_id, {"comment": "", "entries": []})
    entries = [dict(row) for row in current.get("entries") or []]
    remaining = [row for row in entries if str(row.get("id") or "") != entry_id]
    if len(remaining) == len(entries):
        return JSONResponse({"error": "Print-only entry not found"}, status_code=404)
    try:
        saved = save_local_content(db, list_id, current.get("comment") or "", remaining)
        return _saved_local_response(db, list_id, saved)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.post("/api/shopping-print/item-overrides")
def shopping_print_save_item_override(body: dict, db: Session = Depends(get_db)):
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
        )
        payload = _full_payload(db, list_id)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
    return {"ok": True, "saved": saved, "item_overrides": payload.get("item_overrides", [])}


@router.post("/api/shopping-print/item-overrides/delete")
def shopping_print_delete_item_override(body: dict, db: Session = Depends(get_db)):
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)
    list_id = str(body.get("list_id") or "").strip()
    if not _valid_list_id(list_id):
        return JSONResponse({"error": "Shopping list not found"}, status_code=404)
    try:
        delete_item_override(db, list_id, str(body.get("key") or ""))
        payload = _full_payload(db, list_id)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
    return {"ok": True, "item_overrides": payload.get("item_overrides", [])}


@router.post("/api/shopping-print/print")
def shopping_print_print(body: dict, db: Session = Depends(get_db)):
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)

    image_base64 = str(body.get("image_base64") or "")
    if image_base64.startswith("data:") and "," in image_base64:
        image_base64 = image_base64.split(",", 1)[1]
    if not image_base64:
        return JSONResponse({"error": "Rendered shopping-list image is required"}, status_code=400)
    if len(image_base64) > 24_000_000:
        return JSONResponse({"error": "Rendered shopping list is too large"}, status_code=413)

    try:
        height_mm = float(body.get("height_mm"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "Invalid rendered paper height"}, status_code=400)
    if not 5 <= height_mm <= 1000:
        return JSONResponse({"error": "Rendered paper height must be between 5 and 1000 mm"}, status_code=400)
    if not niim_is_configured():
        return JSONResponse({"error": "NIIMBOT printing is not configured"}, status_code=400)

    cfg = load_print_settings(db)
    try:
        result = print_image_base64(
            image_base64,
            width_mm=cfg["paper_width_mm"],
            height_mm=height_mm,
            quantity=1,
            density=cfg["density"],
            label_type=cfg["label_type"],
            dpi=cfg["dpi"],
            threshold=cfg["threshold"],
        )
        return {"ok": True, "height_mm": round(height_mm, 1), **result}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
