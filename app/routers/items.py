import json
import logging
from collections import Counter
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Activity, BarcodeCache, BarcodeMapping, Item
from app.services.mealie import get_food, update_food
from app.services.mealie_extras import (
    cached_labels,
    clear_catalog_cache,
    refresh_open_shopping_items_for_food,
    sync_items_enhanced,
)
from app.services.shopping import get_shopping_lists
from app.templating import _localtime, _relative_time, templates
from app.utils import utcnow

logger = logging.getLogger(__name__)
router = APIRouter()


def _item_scan_stats(db: Session, item_id: str) -> dict:
    scans = (
        db.query(Activity)
        .filter(
            Activity.is_scan_event == True,
            Activity.target_type == "food",
            Activity.target_id == item_id,
        )
        .order_by(Activity.created_at.desc())
        .all()
    )
    now = utcnow().replace(tzinfo=None)
    by_barcode = Counter()
    last_by_barcode = {}
    for row in scans:
        by_barcode[row.barcode] += 1
        if row.barcode not in last_by_barcode:
            last_by_barcode[row.barcode] = row.created_at
    return {
        "total": len(scans),
        "days_7": sum(1 for row in scans if row.created_at and row.created_at >= now - timedelta(days=7)),
        "days_30": sum(1 for row in scans if row.created_at and row.created_at >= now - timedelta(days=30)),
        "last_scan": scans[0].created_at if scans else None,
        "first_scan": scans[-1].created_at if scans else None,
        "recent": scans[:25],
        "by_barcode": [
            {"barcode": barcode, "count": count, "last_scan": last_by_barcode.get(barcode)}
            for barcode, count in by_barcode.most_common()
        ],
    }


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
    query = db.query(Item)
    if q:
        query = query.filter(Item.name.ilike(f"%{q}%") | Item.aliases.ilike(f"%{q}%"))
    all_items = query.all()

    mapping_counts = Counter()
    for mapping in db.query(BarcodeMapping).filter(BarcodeMapping.target_type == "food").all():
        mapping_counts[mapping.target_id] += 1

    scan_rows = (
        db.query(Activity.target_id, func.count(Activity.id), func.max(Activity.created_at))
        .filter(Activity.is_scan_event == True, Activity.target_type == "food", Activity.target_id.isnot(None))
        .group_by(Activity.target_id)
        .all()
    )
    scan_counts = {row[0]: int(row[1]) for row in scan_rows}
    last_scans = {row[0]: row[2] for row in scan_rows}

    entries = []
    for item in all_items:
        mapping_count = mapping_counts.get(item.id, 0)
        scan_count = scan_counts.get(item.id, 0)
        if filter == "linked" and mapping_count == 0:
            continue
        if filter == "unlinked" and mapping_count > 0:
            continue
        if filter == "scanned" and scan_count == 0:
            continue
        if filter == "never" and scan_count > 0:
            continue
        if filter == "mealie" and item.source != "mealie":
            continue
        if filter == "manual" and item.source != "manual":
            continue
        if label and item.label_id != label:
            continue
        entries.append({
            "item": item,
            "mapping_count": mapping_count,
            "scan_count": scan_count,
            "last_scan": last_scans.get(item.id),
        })

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
        {(i.label_id, i.label_name) for i in all_items if i.label_id and i.label_name},
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

    mappings = db.query(BarcodeMapping).filter(
        BarcodeMapping.target_type == "food",
        BarcodeMapping.target_id == item_id,
    ).all()
    barcode_ids = [m.barcode for m in mappings]
    barcodes = db.query(BarcodeCache).filter(BarcodeCache.barcode.in_(barcode_ids)).all() if barcode_ids else []
    barcode_map = {bc.barcode: bc for bc in barcodes}
    mapped_items = [{"mapping": mapping, "barcode": barcode_map.get(mapping.barcode)} for mapping in mappings]

    mealie_food = get_food(item_id) if item.source == "mealie" else None
    labels = cached_labels() if item.source == "mealie" else []
    current_label_id = None
    if mealie_food:
        current_label_id = mealie_food.get("labelId")
        if not current_label_id and isinstance(mealie_food.get("label"), dict):
            current_label_id = mealie_food["label"].get("id")

    return templates.TemplateResponse(request, "item_detail.html", {
        "item": item,
        "mapped_items": mapped_items,
        "mealie_food": mealie_food,
        "labels": labels,
        "current_label_id": current_label_id,
        "stats": _item_scan_stats(db, item_id),
        "shopping_lists": get_shopping_lists(),
        "default_shopping_list_id": settings.mealie_shopping_list_id,
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
        food = update_food(
            item_id,
            name=name,
            plural_name=plural_name.strip() or None,
            description=description.strip() or None,
            label_id=label_id or None,
        )
    except Exception:
        logger.exception("Failed to update Mealie Food %s", item_id)
        return RedirectResponse(f"/items/{item_id}?edit_error=1", status_code=303)

    aliases_raw = food.get("aliases") or []
    aliases = [a.get("name", a) if isinstance(a, dict) else a for a in aliases_raw]
    returned_label = food.get("label") if isinstance(food.get("label"), dict) else None
    item.name = food.get("name") or name
    item.aliases = json.dumps(aliases)
    item.label_id = food.get("labelId") or (returned_label.get("id") if returned_label else None) or (label_id or None)
    item.label_name = returned_label.get("name") if returned_label else next(
        (label.get("name") for label in cached_labels() if label.get("id") == item.label_id), None,
    )
    item.updated_at = utcnow()
    item.synced_at = utcnow()
    db.query(BarcodeMapping).filter(
        BarcodeMapping.target_type == "food",
        BarcodeMapping.target_id == item_id,
    ).update({"target_name": item.name})
    db.commit()

    clear_catalog_cache()
    background_tasks.add_task(refresh_open_shopping_items_for_food, item_id)
    return RedirectResponse(f"/items/{item_id}?saved=1", status_code=303)


@router.post("/items/{item_id}/remove-mapping/{barcode}")
def remove_item_mapping(item_id: str, barcode: str, db: Session = Depends(get_db)):
    mapping = db.get(BarcodeMapping, barcode)
    if mapping and mapping.target_type == "food" and mapping.target_id == item_id:
        db.delete(mapping)
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
    db.query(BarcodeMapping).filter(
        BarcodeMapping.target_type == "food",
        BarcodeMapping.target_id == item_id,
    ).delete()
    db.delete(item)
    db.commit()
    return RedirectResponse("/items", status_code=303)
