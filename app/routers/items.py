import json
import logging
from collections import defaultdict

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BarcodeCache, BarcodeTarget, Item
from app.services.mealie import get_food, update_food
from app.services.mealie_extras import (
    cached_labels,
    clear_catalog_cache,
    refresh_open_shopping_items_for_food,
    sync_items_enhanced,
)
from app.services.scan_stats import target_scan_stats, target_usage_summary
from app.services.shopping import get_default_shopping_list_id, get_shopping_lists
from app.templating import _localtime, _relative_time, templates
from app.utils import utcnow

logger = logging.getLogger(__name__)
router = APIRouter()


def _item_scan_stats(db: Session, item_id: str) -> dict:
    return target_scan_stats(db, "food", item_id, recent_limit=25)


def _stats_json(stats: dict) -> dict:
    return {
        "total": stats["total"],
        "days_7": stats["days_7"],
        "days_30": stats["days_30"],
        "last_scan": _relative_time(stats["last_scan"]),
        "last_scan_absolute": _localtime(stats["last_scan"]),
        "first_scan": _relative_time(stats["first_scan"]),
        "by_barcode": [
            {
                "barcode": row["barcode"],
                "count": row["count"],
                "last_scan": _relative_time(row["last_scan"]),
                "last_scan_absolute": _localtime(row["last_scan"]),
            }
            for row in stats["by_barcode"]
        ],
    }


@router.get("/api/items/{item_id}/stats")
def item_stats_api(item_id: str, db: Session = Depends(get_db)):
    if not db.get(Item, item_id):
        return JSONResponse({"error": "Item not found"}, status_code=404)
    return _stats_json(_item_scan_stats(db, item_id))


def _item_list_entries(db: Session, q: str, filter_value: str, label: str) -> tuple[list[dict], list[Item]]:
    query = db.query(Item)
    if q:
        query = query.filter(Item.name.ilike(f"%{q}%") | Item.aliases.ilike(f"%{q}%"))
    all_items = query.all()

    barcode_sets: dict[str, set[str]] = defaultdict(set)
    targets = db.query(BarcodeTarget).filter(BarcodeTarget.target_type == "food", BarcodeTarget.enabled == True).all()
    for target in targets:
        barcode_sets[str(target.target_id)].add(target.barcode)

    scan_stats = target_usage_summary(db, "food")
    entries = []
    for item in all_items:
        mapping_count = len(barcode_sets.get(str(item.id), set()))
        usage = scan_stats.get(str(item.id), {})
        scan_count = int(usage.get("count") or 0)
        last_scan = usage.get("last_scan")
        if filter_value == "linked" and mapping_count == 0:
            continue
        if filter_value == "unlinked" and mapping_count > 0:
            continue
        if filter_value == "scanned" and scan_count == 0:
            continue
        if filter_value == "never" and scan_count > 0:
            continue
        if filter_value == "mealie" and item.source != "mealie":
            continue
        if filter_value == "manual" and item.source != "manual":
            continue
        if label and item.label_id != label:
            continue
        entries.append({"item": item, "mapping_count": mapping_count, "scan_count": scan_count, "last_scan": last_scan})
    return entries, all_items


@router.get("/items", response_class=HTMLResponse)
def items_list(
    request: Request,
    q: str = Query(""),
    sort: str = Query("name"),
    order: str = Query("asc"),
    filter: str = Query("all"),
    label: str = Query(""),
    db: Session = Depends(get_db),
):
    entries, all_items = _item_list_entries(db, q, filter, label)
    reverse = order == "desc"
    key_map = {
        "name": lambda e: (e["item"].name or "").casefold(),
        "updated": lambda e: e["item"].updated_at or e["item"].created_at,
        "last_scan": lambda e: e["last_scan"] or e["item"].created_at,
        "scans": lambda e: e["scan_count"],
        "barcodes": lambda e: e["mapping_count"],
        "category": lambda e: (e["item"].label_name or "").casefold(),
    }
    entries.sort(key=key_map.get(sort, key_map["name"]), reverse=reverse)
    synced_values = [i.synced_at for i in all_items if i.source == "mealie" and i.synced_at]
    last_synced = max(synced_values) if synced_values else None
    labels = sorted(
        {(i.label_id, i.label_name) for i in db.query(Item).all() if i.label_id and i.label_name},
        key=lambda row: row[1].casefold(),
    )
    return templates.TemplateResponse(request, "items.html", {
        "items": entries,
        "search_query": q,
        "last_synced": last_synced,
        "current_sort": sort,
        "current_order": order,
        "current_filter": filter,
        "current_label": label,
        "labels": labels,
    })


@router.get("/items/{item_id}", response_class=HTMLResponse)
def item_detail(request: Request, item_id: str, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if not item:
        return templates.TemplateResponse(request, "404.html", {"message": "Item not found"}, status_code=404)

    target_rows = (
        db.query(BarcodeTarget)
        .filter(BarcodeTarget.target_type == "food", BarcodeTarget.target_id == item_id)
        .order_by(BarcodeTarget.barcode, BarcodeTarget.position, BarcodeTarget.id)
        .all()
    )
    by_barcode = {}
    for target in target_rows:
        by_barcode.setdefault(target.barcode, target)
    barcode_ids = list(by_barcode)
    barcodes = db.query(BarcodeCache).filter(BarcodeCache.barcode.in_(barcode_ids)).all() if barcode_ids else []
    barcode_map = {bc.barcode: bc for bc in barcodes}
    mapped_items = [{"mapping": row, "barcode": barcode_map.get(barcode)} for barcode, row in by_barcode.items()]

    mealie_food = get_food(item_id) if item.source == "mealie" else None
    labels = cached_labels() if item.source == "mealie" else []
    current_label_id = None
    if mealie_food:
        current_label_id = mealie_food.get("labelId")
        if not current_label_id and isinstance(mealie_food.get("label"), dict):
            current_label_id = mealie_food["label"].get("id")

    shopping_lists = get_shopping_lists()
    default_shopping_list_id = get_default_shopping_list_id(db)
    default_shopping_list_name = next(
        (row["name"] for row in shopping_lists if row["id"] == str(default_shopping_list_id)),
        None,
    )

    return templates.TemplateResponse(request, "item_detail.html", {
        "item": item,
        "mapped_items": mapped_items,
        "mealie_food": mealie_food,
        "labels": labels,
        "current_label_id": current_label_id,
        "stats": _item_scan_stats(db, item_id),
        "shopping_lists": shopping_lists,
        "default_shopping_list_id": default_shopping_list_id,
        "default_shopping_list_name": default_shopping_list_name,
        "saved": request.query_params.get("saved") == "1",
        "routing_saved": request.query_params.get("routing_saved") == "1",
        "edit_error": request.query_params.get("edit_error") == "1",
    })


@router.post("/items/{item_id}/routing")
def save_item_routing(
    item_id: str,
    shopping_route: str = Form("default"),
    shopping_list_id: str = Form(""),
    db: Session = Depends(get_db),
):
    item = db.get(Item, item_id)
    if not item:
        return RedirectResponse("/items", status_code=303)
    route = shopping_route.strip().lower()
    if route not in {"default", "mealie", "homeassistant", "both", "none"}:
        route = "default"
    item.shopping_route = route
    item.shopping_list_id = shopping_list_id.strip() or None
    item.updated_at = utcnow()
    db.commit()
    return RedirectResponse(f"/items/{item_id}?routing_saved=1", status_code=303)


@router.post("/items/{item_id}/edit")
def edit_mealie_item(
    item_id: str,
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    plural_name: str = Form(""),
    description: str = Form(""),
    label_id: str = Form(""),
    db: Session = Depends(get_db),
):
    item = db.get(Item, item_id)
    name = name.strip()
    if not item or item.source != "mealie" or not name:
        return RedirectResponse(f"/items/{item_id}?edit_error=1", status_code=303)
    try:
        food = update_food(item_id, name=name, plural_name=plural_name.strip() or None, description=description.strip() or None, label_id=label_id or None)
    except Exception:
        logger.exception("Failed to update Mealie Food %s", item_id)
        return RedirectResponse(f"/items/{item_id}?edit_error=1", status_code=303)

    aliases_raw = food.get("aliases") or []
    aliases = [a.get("name", a) if isinstance(a, dict) else a for a in aliases_raw]
    returned_label = food.get("label") if isinstance(food.get("label"), dict) else None
    returned_unit = food.get("unit") if isinstance(food.get("unit"), dict) else None
    item.name = food.get("name") or name
    item.aliases = json.dumps(aliases)
    item.label_id = food.get("labelId") or (returned_label.get("id") if returned_label else None) or (label_id or None)
    item.label_name = returned_label.get("name") if returned_label else next((label.get("name") for label in cached_labels() if label.get("id") == item.label_id), None)
    item.default_unit_id = food.get("unitId") or (returned_unit.get("id") if returned_unit else item.default_unit_id)
    item.default_unit_name = returned_unit.get("name") if returned_unit else item.default_unit_name
    item.updated_at = utcnow()
    item.synced_at = utcnow()
    db.query(BarcodeTarget).filter(BarcodeTarget.target_type == "food", BarcodeTarget.target_id == item_id).update({"target_name": item.name})
    db.commit()
    clear_catalog_cache()
    background_tasks.add_task(refresh_open_shopping_items_for_food, item_id)
    return RedirectResponse(f"/items/{item_id}?saved=1", status_code=303)


@router.post("/items/{item_id}/remove-mapping/{barcode}")
def remove_item_mapping(item_id: str, barcode: str, db: Session = Depends(get_db)):
    db.query(BarcodeTarget).filter(
        BarcodeTarget.barcode == barcode,
        BarcodeTarget.target_type == "food",
        BarcodeTarget.target_id == item_id,
    ).delete()
    db.commit()
    return RedirectResponse(f"/items/{item_id}", status_code=303)


@router.post("/items/sync")
def trigger_sync(db: Session = Depends(get_db)):
    try:
        sync_items_enhanced(db)
    except Exception as e:
        logger.error("Manual item sync failed: %s", e)
    return RedirectResponse("/items", status_code=303)


@router.post("/items/add")
def add_custom_item(name: str = Form(...), db: Session = Depends(get_db)):
    name = name.strip()
    if name:
        db.add(Item(name=name, source="manual", updated_at=utcnow()))
        db.commit()
    return RedirectResponse("/items", status_code=303)


@router.post("/items/{item_id}/delete")
def delete_custom_item(item_id: str, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if not item or item.source != "manual":
        return RedirectResponse("/items", status_code=303)
    db.query(BarcodeTarget).filter(BarcodeTarget.target_type == "food", BarcodeTarget.target_id == item_id).delete()
    db.delete(item)
    db.commit()
    return RedirectResponse("/items", status_code=303)
