import json
import logging
from collections import Counter
from datetime import timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Activity, BarcodeCache, BarcodeTarget, Item, RetryQueue
from app.services.barcode_lookup import perform_lookup
from app.services.fuzzy import fuzzy_match
from app.services.homeassistant import dismiss_notification as ha_dismiss
from app.services.mealie import create_food, find_food_by_name, reconcile_linked_barcode, search_recipes
from app.services.mealie_extras import cached_labels, cached_units
from app.services.shopping import get_default_shopping_list_id, get_shopping_lists
from app.services.targets import add_target, ensure_targets, list_ids, primary_targets_by_barcode, set_list_ids
from app.templating import templates
from app.utils import utcnow

logger = logging.getLogger(__name__)
router = APIRouter()


def _parse_positive_float(value: str | float | int | None, default: float = 1.0) -> float:
    if value is None:
        return round(default, 3)
    try:
        parsed = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return round(default, 3)
    return max(round(parsed, 3), 0.001)


def _parse_optional_quantity(value: str | float | int | None) -> float | None:
    raw = "" if value is None else str(value).strip().replace(",", ".")
    if not raw:
        return None
    try:
        parsed = float(raw)
    except ValueError:
        return None
    if parsed <= 0.001:
        return None
    return round(parsed, 3)


def _is_database_locked(exc: OperationalError) -> bool:
    return "database is locked" in str(exc).casefold()


def _naive_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _mark_notifications_read(barcode: str, db: Session):
    db.query(Activity).filter(Activity.barcode == barcode, Activity.is_read == False).update({"is_read": True}, synchronize_session=False)


def _resolve_activity_state(barcode: str, target_name: str | None, db: Session) -> None:
    rows = db.query(Activity).filter(
        Activity.barcode == barcode,
        Activity.is_scan_event == False,
        Activity.result.in_(["needs_mapping", "unknown", "auto_mapped", "broken"]),
    ).all()
    for row in rows:
        row.title = "Linked"
        row.message = f"Now linked to {target_name or 'a target'}"
        row.result = "resolved"
        row.is_read = True
        row.is_dismissed = True


def _resolve_notifications_async(barcode: str, target_name: str | None, background_tasks: BackgroundTasks, db: Session):
    try:
        _mark_notifications_read(barcode, db)
        _resolve_activity_state(barcode, target_name, db)
        db.commit()
    except OperationalError as exc:
        db.rollback()
        if not _is_database_locked(exc):
            raise
        logger.warning("Skipping activity resolution for barcode %s because SQLite is busy", barcode)
    background_tasks.add_task(ha_dismiss, barcode, None)


def _food_label(food: dict) -> tuple[str | None, str | None]:
    label = food.get("label")
    if isinstance(label, dict):
        return label.get("id"), label.get("name")
    return food.get("labelId"), None


def _food_unit(food: dict) -> tuple[str | None, str | None]:
    unit = food.get("unit")
    if isinstance(unit, dict):
        return food.get("unitId") or unit.get("id"), unit.get("name") or unit.get("abbreviation")
    return food.get("unitId"), None


def _cache_food(food: dict, db: Session) -> Item:
    aliases_raw = food.get("aliases") or []
    aliases = [a.get("name", a) if isinstance(a, dict) else a for a in aliases_raw]
    label_id, label_name = _food_label(food)
    unit_id, unit_name = _food_unit(food)
    now = utcnow()
    existing = db.get(Item, food["id"])
    if existing:
        existing.name = food.get("name") or "Unnamed Food"
        existing.aliases = json.dumps(aliases)
        existing.label_id = label_id
        existing.label_name = label_name
        existing.default_unit_id = unit_id
        existing.default_unit_name = unit_name
        existing.source = "mealie"
        existing.synced_at = now
        existing.updated_at = now
        item = existing
    else:
        item = Item(
            id=food["id"], name=food.get("name") or "Unnamed Food", source="mealie",
            aliases=json.dumps(aliases), label_id=label_id, label_name=label_name,
            default_unit_id=unit_id, default_unit_name=unit_name,
            synced_at=now, updated_at=now,
        )
        db.add(item)
    db.flush()
    return item


def _barcode_stats(db: Session, barcode: str) -> dict:
    scans = db.query(Activity).filter(Activity.is_scan_event == True, Activity.barcode == barcode).order_by(Activity.created_at.desc()).all()
    now = _naive_utc(utcnow())
    results = Counter(row.result for row in scans)
    return {
        "total": len(scans),
        "days_7": sum(1 for row in scans if row.created_at and _naive_utc(row.created_at) >= now - timedelta(days=7)),
        "days_30": sum(1 for row in scans if row.created_at and _naive_utc(row.created_at) >= now - timedelta(days=30)),
        "last_scan": scans[0].created_at if scans else None,
        "first_scan": scans[-1].created_at if scans else None,
        "results": results,
        "recent": scans[:25],
    }


def _mapped_subquery(db: Session):
    return db.query(BarcodeTarget.barcode).filter(BarcodeTarget.enabled == True).distinct()


def _apply_status_filter(query, status: str, mapped_sub):
    if status == "mapped":
        return query.filter((BarcodeCache.barcode.in_(mapped_sub)) | (BarcodeCache.source == "action"))
    if status == "pending":
        return query.filter(BarcodeCache.found == True, BarcodeCache.source != "action", ~BarcodeCache.barcode.in_(mapped_sub))
    if status == "unknown":
        return query.filter(BarcodeCache.found == False, BarcodeCache.source != "action", ~BarcodeCache.barcode.in_(mapped_sub))
    return query


@router.get("/barcodes", response_class=HTMLResponse)
def barcodes_list(request: Request, status: str = Query(default="all"), db: Session = Depends(get_db)):
    query = db.query(BarcodeCache).order_by(BarcodeCache.created_at.desc())
    mapped_sub = _mapped_subquery(db)
    barcodes = _apply_status_filter(query, status, mapped_sub).all()
    mappings = primary_targets_by_barcode(db)
    target_counts = Counter(row.barcode for row in db.query(BarcodeTarget).filter(BarcodeTarget.enabled == True).all())
    queued_barcodes = {r.barcode for r in db.query(RetryQueue).all()}
    food_ids = [m.target_id for m in mappings.values() if m.target_type == "food"]
    foods_map = {i.id: i for i in db.query(Item).filter(Item.id.in_(food_ids)).all()} if food_ids else {}
    items = []
    for bc in barcodes:
        mapping = mappings.get(bc.barcode)
        food = foods_map.get(mapping.target_id) if mapping and mapping.target_type == "food" else None
        if mapping:
            bc_status = "mapped"
        elif bc.source == "action":
            bc_status = "action"
        elif bc.barcode in queued_barcodes:
            bc_status = "queued"
        elif not bc.found:
            bc_status = "unknown"
        else:
            bc_status = "pending"
        items.append({
            "barcode": bc, "mapping": mapping, "item": food,
            "target_name": mapping.target_name if mapping else None,
            "target_type": mapping.target_type if mapping else None,
            "target_count": target_counts.get(bc.barcode, 1 if mapping else 0),
            "status": bc_status,
        })
    return templates.TemplateResponse(request, "barcodes.html", {"items": items, "current_status": status})


@router.post("/barcodes/new")
def barcode_create_manual(code: str = Form(...), title: str = Form(""), brand: str = Form(""), db: Session = Depends(get_db)):
    code = code.strip()
    if not code:
        return RedirectResponse("/barcodes", status_code=303)
    cached = db.get(BarcodeCache, code)
    if not cached:
        now = utcnow()
        cached = BarcodeCache(
            barcode=code, source="manual", title=title.strip() or None, brand=brand.strip() or None,
            custom_title=title.strip() or None, custom_brand=brand.strip() or None,
            found=bool(title.strip()), lookup_attempted_at=now, created_at=now,
        )
        db.add(cached)
    else:
        if title.strip(): cached.custom_title = title.strip()
        if brand.strip(): cached.custom_brand = brand.strip()
        if title.strip(): cached.found = True
    db.commit()
    return RedirectResponse(f"/barcodes/{quote(code, safe='')}", status_code=303)


@router.get("/barcodes/{barcode:path}", response_class=HTMLResponse)
def barcode_detail(request: Request, barcode: str, db: Session = Depends(get_db)):
    cached = db.get(BarcodeCache, barcode)
    targets = ensure_targets(barcode, db)
    mapping = next((target for target in targets if target.enabled), targets[0] if targets else None)
    mapped_item = db.get(Item, mapping.target_id) if mapping and mapping.target_type == "food" else None
    try:
        _mark_notifications_read(barcode, db)
        db.commit()
    except OperationalError as exc:
        db.rollback()
        if not _is_database_locked(exc):
            raise
        logger.warning("Barcode %s rendered while SQLite was busy; notification read mark deferred", barcode)

    candidates = fuzzy_match(cached.display_title, cached.display_brand, db)[:6] if cached and cached.display_title else []
    mapped_barcodes = _mapped_subquery(db)
    next_unmapped = (
        db.query(BarcodeCache)
        .filter(~BarcodeCache.barcode.in_(mapped_barcodes))
        .filter(BarcodeCache.source != "action", BarcodeCache.barcode != barcode)
        .order_by(BarcodeCache.created_at.desc()).first()
    )
    shopping_lists = get_shopping_lists()
    default_list_id = get_default_shopping_list_id(db)
    target_views = []
    for target in targets:
        item = db.get(Item, target.target_id) if target.target_type == "food" else None
        target_views.append({"target": target, "item": item, "list_ids": list_ids(target)})

    return templates.TemplateResponse(request, "barcode_detail.html", {
        "cached": cached,
        "mapping": mapping,
        "targets": target_views,
        "mapped_item": mapped_item,
        "is_confirmed": bool(mapping and mapping.mapped_by in ("manual", "auto_confirmed", "generic")),
        "candidates": candidates,
        "next_unmapped": next_unmapped,
        "threshold": settings.fuzzy_match_threshold,
        "units": cached_units(),
        "labels": cached_labels(),
        "shopping_lists": shopping_lists,
        "default_shopping_list_id": default_list_id,
        "stats": _barcode_stats(db, barcode),
        "duplicate_food": request.query_params.get("duplicate_food") == "1",
        "create_error": request.query_params.get("create_error") == "1",
        "metadata_saved": request.query_params.get("metadata_saved") == "1",
    })


@router.post("/barcodes/{barcode:path}/metadata")
async def barcode_metadata(request: Request, barcode: str, db: Session = Depends(get_db)):
    form = await request.form()
    cached = db.get(BarcodeCache, barcode)
    if cached:
        cached.custom_title = str(form.get("title") or "").strip() or None
        cached.custom_brand = str(form.get("brand") or "").strip() or None
        cached.found = bool(cached.display_title)
        db.commit()
    if request.headers.get("x-requested-with") == "fetch":
        return JSONResponse({"ok": True, "title": cached.display_title if cached else None, "brand": cached.display_brand if cached else None})
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}?metadata_saved=1", status_code=303)


@router.post("/barcodes/{barcode:path}/refresh-lookup")
def barcode_refresh_lookup(barcode: str, db: Session = Depends(get_db)):
    cached = db.get(BarcodeCache, barcode)
    if cached:
        cached.custom_title = None
        cached.custom_brand = None
        db.commit()
    if barcode.isdigit():
        perform_lookup(barcode, db)
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/map")
def barcode_map(
    barcode: str,
    background_tasks: BackgroundTasks,
    item_id: str = Form(...),
    quantity: str = Form(""),
    unit_id: str = Form(""),
    route: str = Form("inherit"),
    shopping_list_ids: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
):
    item = db.get(Item, item_id)
    if not item or item.source != "mealie":
        return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)
    effective_unit = item.default_unit_id if unit_id in {"", "__item_default__"} else unit_id
    target = add_target(barcode, "food", item.id, item.name, db, route=route, list_ids_value=shopping_list_ids, quantity=_parse_optional_quantity(quantity), unit_id=effective_unit)
    _resolve_notifications_async(barcode, target.target_name, background_tasks, db)
    background_tasks.add_task(reconcile_linked_barcode, barcode)
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/create-and-map")
def barcode_create_and_map(
    barcode: str,
    background_tasks: BackgroundTasks,
    name: str = Form(...), plural_name: str = Form(""), description: str = Form(""), label_id: str = Form(""),
    quantity: str = Form(""), unit_id: str = Form(""), route: str = Form("inherit"),
    shopping_list_ids: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
):
    name = name.strip()
    if not name:
        return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)
    food = find_food_by_name(name)
    duplicate = food is not None
    if not food:
        try:
            food = create_food(name=name, plural_name=plural_name.strip() or None, description=description.strip() or None, label_id=label_id or None)
        except Exception:
            food = find_food_by_name(name)
            if not food:
                logger.exception("Failed to create Mealie Food for barcode %s", barcode)
                return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}?create_error=1", status_code=303)
            duplicate = True
    item = _cache_food(food, db)
    effective_unit = item.default_unit_id if unit_id in {"", "__item_default__"} else unit_id
    target = add_target(barcode, "food", item.id, item.name, db, route=route, list_ids_value=shopping_list_ids, quantity=_parse_optional_quantity(quantity), unit_id=effective_unit)
    _resolve_notifications_async(barcode, target.target_name, background_tasks, db)
    background_tasks.add_task(reconcile_linked_barcode, barcode)
    suffix = "?duplicate_food=1" if duplicate else ""
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}{suffix}", status_code=303)


@router.post("/barcodes/{barcode:path}/map-recipe")
def barcode_map_recipe(
    barcode: str,
    background_tasks: BackgroundTasks,
    recipe_id: str = Form(...), recipe_name: str = Form(""), recipe_scale: str = Form("1"),
    route: str = Form("mealie"), shopping_list_ids: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
):
    recipe_id = recipe_id.strip()
    if not recipe_id:
        return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)
    target = add_target(barcode, "recipe", recipe_id, recipe_name.strip() or recipe_id, db, route=route, list_ids_value=shopping_list_ids, quantity=None, recipe_scale=_parse_positive_float(recipe_scale))
    _resolve_notifications_async(barcode, target.target_name, background_tasks, db)
    background_tasks.add_task(reconcile_linked_barcode, barcode)
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/targets/{target_id}")
def barcode_target_settings(
    barcode: str,
    target_id: int,
    quantity: str = Form(""), unit_id: str = Form(""), recipe_scale: str = Form("1"),
    route: str = Form("inherit"), shopping_list_ids: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
):
    target = db.get(BarcodeTarget, target_id)
    if target and target.barcode == barcode:
        target.route = route if route in {"inherit", "mealie", "homeassistant", "both", "none"} else "inherit"
        set_list_ids(target, shopping_list_ids)
        if target.target_type == "food":
            item = db.get(Item, target.target_id)
            target.quantity = _parse_optional_quantity(quantity)
            target.unit_id = (item.default_unit_id if item and unit_id in {"", "__item_default__"} else (unit_id or None))
        else:
            target.recipe_scale = _parse_positive_float(recipe_scale)
        db.commit()
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/targets/{target_id}/delete")
def barcode_target_delete(barcode: str, target_id: int, db: Session = Depends(get_db)):
    target = db.get(BarcodeTarget, target_id)
    if target and target.barcode == barcode:
        db.delete(target)
        db.commit()
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/mapping-settings")
def barcode_mapping_settings(
    barcode: str,
    quantity: str = Form(""), unit_id: str = Form(""), recipe_scale: str = Form("1"), shopping_list_id: str = Form(""),
    db: Session = Depends(get_db),
):
    targets = ensure_targets(barcode, db)
    if targets:
        target = targets[0]
        if target.target_type == "food":
            target.quantity = _parse_optional_quantity(quantity)
            target.unit_id = unit_id or None
        else:
            target.recipe_scale = _parse_positive_float(recipe_scale)
            set_list_ids(target, [shopping_list_id] if shopping_list_id else [])
        db.commit()
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/confirm")
def barcode_confirm(barcode: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    targets = ensure_targets(barcode, db)
    changed = False
    target_name = None
    for target in targets:
        if target.mapped_by == "auto":
            target.mapped_by = "auto_confirmed"
            target_name = target_name or target.target_name
            changed = True
    if changed:
        db.commit()
        _resolve_notifications_async(barcode, target_name, background_tasks, db)
        background_tasks.add_task(reconcile_linked_barcode, barcode)
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/unmap")
def barcode_unmap(barcode: str, db: Session = Depends(get_db)):
    db.query(BarcodeTarget).filter(BarcodeTarget.barcode == barcode).delete()
    db.commit()
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/retry-lookup")
def barcode_retry_lookup(barcode: str, db: Session = Depends(get_db)):
    if barcode.isdigit():
        perform_lookup(barcode, db)
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/delete")
def barcode_delete(barcode: str, db: Session = Depends(get_db)):
    db.query(RetryQueue).filter(RetryQueue.barcode == barcode).delete()
    db.query(BarcodeTarget).filter(BarcodeTarget.barcode == barcode).delete()
    cached = db.get(BarcodeCache, barcode)
    if cached:
        db.delete(cached)
    db.commit()
    return RedirectResponse("/barcodes", status_code=303)


@router.get("/barcodes-search")
def barcodes_search(q: str = Query(default=""), db: Session = Depends(get_db)):
    q = q.strip()
    if not q:
        return []
    return [{
        "id": row["item_id"], "name": row["item_name"], "source": row["source"],
        "score": row["score"], "exact": row.get("exact", False),
        "default_unit_id": row.get("default_unit_id"), "default_unit_name": row.get("default_unit_name"),
    } for row in fuzzy_match(q, None, db)[:6]]


@router.get("/recipes-search")
def recipes_search(q: str = Query(default="")):
    return search_recipes(q.strip(), limit=6)


@router.get("/api/barcodes")
def barcodes_api(status: str = "all", db: Session = Depends(get_db)):
    from app.templating import _localtime
    query = db.query(BarcodeCache).order_by(BarcodeCache.created_at.desc())
    mapped_sub = _mapped_subquery(db)
    barcodes = _apply_status_filter(query, status, mapped_sub).limit(200).all()
    mappings = primary_targets_by_barcode(db)
    target_counts = Counter(row.barcode for row in db.query(BarcodeTarget).filter(BarcodeTarget.enabled == True).all())
    queued_barcodes = {r.barcode for r in db.query(RetryQueue).all()}
    result_items = []
    for bc in barcodes:
        mapping = mappings.get(bc.barcode)
        if mapping: bc_status = "mapped"
        elif bc.source == "action": bc_status = "action"
        elif bc.barcode in queued_barcodes: bc_status = "queued"
        elif not bc.found: bc_status = "unknown"
        else: bc_status = "pending"
        target_name = mapping.target_name if mapping else None
        target_id = mapping.target_id if mapping else None
        target_type = mapping.target_type if mapping else ("action" if bc.source == "action" else None)
        if target_type == "action" and not target_id and bc.barcode.upper().startswith("ACTION:"):
            target_id = bc.barcode[7:]
            target_name = bc.display_title or target_id
        result_items.append({
            "barcode": bc.barcode, "title": bc.display_title or "—", "brand": bc.display_brand or "—",
            "source": bc.source or "—", "status": bc_status,
            "target_name": target_name, "target_id": target_id, "target_type": target_type,
            "target_count": target_counts.get(bc.barcode, 1 if mapping else 0),
            "mapped_by": mapping.mapped_by if mapping else None,
            "item_name": target_name if target_type == "food" else None,
            "item_id": target_id if target_type == "food" else None,
            "created_at": _localtime(bc.created_at),
        })
    return {"items": result_items}
