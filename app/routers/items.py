import json
import logging

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BarcodeCache, BarcodeMapping, Item
from app.services.mealie import get_food, get_labels, sync_items, update_food
from app.templating import templates
from app.utils import utcnow

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/items", response_class=HTMLResponse)
def items_list(request: Request, q: str = Query(""), db: Session = Depends(get_db)):
    query = db.query(Item)
    if q:
        query = query.filter(Item.name.ilike(f"%{q}%") | Item.aliases.ilike(f"%{q}%"))
    all_items = query.order_by(func.lower(Item.name)).all()

    mapping_counts = {}
    for mapping in db.query(BarcodeMapping).filter(BarcodeMapping.target_type == "food").all():
        mapping_counts[mapping.target_id] = mapping_counts.get(mapping.target_id, 0) + 1

    items = [{"item": i, "mapping_count": mapping_counts.get(i.id, 0)} for i in all_items]
    last_synced = next((i.synced_at for i in all_items if i.source == "mealie" and i.synced_at), None)

    return templates.TemplateResponse(request, "items.html", {
        "items": items,
        "search_query": q,
        "last_synced": last_synced,
    })


@router.get("/items/{item_id}", response_class=HTMLResponse)
def item_detail(request: Request, item_id: str, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if not item:
        return templates.TemplateResponse(
            request,
            "404.html",
            {"message": "Item not found"},
            status_code=404,
        )

    mappings = db.query(BarcodeMapping).filter(
        BarcodeMapping.target_type == "food",
        BarcodeMapping.target_id == item_id,
    ).all()
    barcode_ids = [m.barcode for m in mappings]
    barcodes = (
        db.query(BarcodeCache).filter(BarcodeCache.barcode.in_(barcode_ids)).all()
        if barcode_ids
        else []
    )
    barcode_map = {bc.barcode: bc for bc in barcodes}
    mapped_items = [
        {"mapping": mapping, "barcode": barcode_map.get(mapping.barcode)}
        for mapping in mappings
    ]

    mealie_food = get_food(item_id) if item.source == "mealie" else None
    labels = get_labels() if item.source == "mealie" else []

    return templates.TemplateResponse(request, "item_detail.html", {
        "item": item,
        "mapped_items": mapped_items,
        "mealie_food": mealie_food,
        "labels": labels,
        "saved": request.query_params.get("saved") == "1",
        "edit_error": request.query_params.get("edit_error") == "1",
    })


@router.post("/items/{item_id}/edit")
def edit_mealie_item(
    item_id: str,
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
    item.name = food.get("name") or name
    item.aliases = json.dumps(aliases)
    item.synced_at = utcnow()
    db.query(BarcodeMapping).filter(
        BarcodeMapping.target_type == "food",
        BarcodeMapping.target_id == item_id,
    ).update({"target_name": item.name})
    db.commit()

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
        sync_items(db)
    except Exception as e:
        logger.error("Manual item sync failed: %s", e)
    return RedirectResponse("/items", status_code=303)


@router.post("/items/add")
def add_custom_item(name: str = Form(...), db: Session = Depends(get_db)):
    """Legacy local item support; barcode mapping UI now creates real Mealie Foods."""
    name = name.strip()
    if name:
        db.add(Item(name=name, source="manual"))
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
