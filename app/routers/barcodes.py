import json
import logging
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Activity, BarcodeCache, BarcodeMapping, Item, RetryQueue
from app.services.barcode_lookup import perform_lookup
from app.services.fuzzy import fuzzy_match
from app.services.homeassistant import dismiss_notification as ha_dismiss
from app.services.mealie import (
    create_food,
    get_labels,
    get_units,
    reconcile_linked_barcode,
    search_recipes,
)
from app.templating import templates
from app.utils import utcnow

logger = logging.getLogger(__name__)
router = APIRouter()


def _mark_notifications_read(barcode: str, db: Session):
    db.query(Activity).filter(
        Activity.barcode == barcode,
        Activity.is_read == False,
    ).update({"is_read": True})


def _resolve_notifications(barcode: str, db: Session):
    _mark_notifications_read(barcode, db)
    ha_dismiss(barcode)


def _food_mapping(
    barcode: str,
    item: Item,
    quantity: float,
    unit_id: str | None,
    db: Session,
    mapped_by: str = "manual",
) -> BarcodeMapping:
    mapping = db.get(BarcodeMapping, barcode)
    if not mapping:
        mapping = BarcodeMapping(
            barcode=barcode,
            target_type="food",
            target_id=item.id,
        )
        db.add(mapping)

    mapping.target_type = "food"
    mapping.target_id = item.id
    mapping.target_name = item.name
    mapping.quantity = max(quantity, 0.000001)
    mapping.unit_id = unit_id or None
    mapping.recipe_scale = 1.0
    mapping.mapped_by = mapped_by
    return mapping


def _recipe_mapping(
    barcode: str,
    recipe_id: str,
    recipe_name: str,
    recipe_scale: float,
    db: Session,
) -> BarcodeMapping:
    mapping = db.get(BarcodeMapping, barcode)
    if not mapping:
        mapping = BarcodeMapping(
            barcode=barcode,
            target_type="recipe",
            target_id=recipe_id,
        )
        db.add(mapping)

    mapping.target_type = "recipe"
    mapping.target_id = recipe_id
    mapping.target_name = recipe_name or recipe_id
    mapping.quantity = 1.0
    mapping.unit_id = None
    mapping.recipe_scale = max(recipe_scale, 0.000001)
    mapping.mapped_by = "manual"
    return mapping


@router.get("/barcodes", response_class=HTMLResponse)
def barcodes_list(
    request: Request,
    status: str = Query(default="all"),
    db: Session = Depends(get_db),
):
    query = db.query(BarcodeCache).order_by(BarcodeCache.created_at.desc())
    mapped_sub = db.query(BarcodeMapping.barcode).subquery()

    if status == "mapped":
        query = query.filter(BarcodeCache.barcode.in_(mapped_sub))
    elif status == "pending":
        query = query.filter(
            BarcodeCache.found == True,
            ~BarcodeCache.barcode.in_(mapped_sub),
        )
    elif status == "unknown":
        query = query.filter(
            BarcodeCache.found == False,
            ~BarcodeCache.barcode.in_(mapped_sub),
        )

    barcodes = query.all()
    mappings = {m.barcode: m for m in db.query(BarcodeMapping).all()}
    queued_barcodes = {r.barcode for r in db.query(RetryQueue).all()}

    food_ids = [m.target_id for m in mappings.values() if m.target_type == "food"]
    foods_map = (
        {i.id: i for i in db.query(Item).filter(Item.id.in_(food_ids)).all()}
        if food_ids
        else {}
    )

    items = []
    for bc in barcodes:
        mapping = mappings.get(bc.barcode)
        food = foods_map.get(mapping.target_id) if mapping and mapping.target_type == "food" else None
        if mapping:
            bc_status = "mapped"
        elif bc.barcode in queued_barcodes:
            bc_status = "queued"
        elif not bc.found:
            bc_status = "unknown"
        else:
            bc_status = "pending"

        items.append({
            "barcode": bc,
            "mapping": mapping,
            "item": food,
            "target_name": mapping.target_name if mapping else None,
            "target_type": mapping.target_type if mapping else None,
            "status": bc_status,
        })

    return templates.TemplateResponse(
        request,
        "barcodes.html",
        {"items": items, "current_status": status},
    )


@router.get("/barcodes/{barcode:path}", response_class=HTMLResponse)
def barcode_detail(
    request: Request,
    barcode: str,
    db: Session = Depends(get_db),
):
    cached = db.get(BarcodeCache, barcode)
    mapping = db.get(BarcodeMapping, barcode)
    mapped_item = (
        db.get(Item, mapping.target_id)
        if mapping and mapping.target_type == "food"
        else None
    )

    _mark_notifications_read(barcode, db)
    db.commit()

    candidates = []
    if cached and cached.title:
        candidates = fuzzy_match(cached.title, cached.brand, db)[:10]

    mapped_barcodes = [m.barcode for m in db.query(BarcodeMapping).all()]
    next_unmapped = (
        db.query(BarcodeCache)
        .filter(~BarcodeCache.barcode.in_(mapped_barcodes))
        .filter(BarcodeCache.barcode != barcode)
        .order_by(BarcodeCache.created_at.desc())
        .first()
    )

    is_confirmed = bool(
        mapping and mapping.mapped_by in ("manual", "auto_confirmed", "generic")
    )

    return templates.TemplateResponse(
        request,
        "barcode_detail.html",
        {
            "cached": cached,
            "mapping": mapping,
            "mapped_item": mapped_item,
            "is_confirmed": is_confirmed,
            "candidates": candidates,
            "next_unmapped": next_unmapped,
            "threshold": settings.fuzzy_match_threshold,
            "units": get_units(),
            "labels": get_labels(),
        },
    )


@router.post("/barcodes/{barcode:path}/map")
def barcode_map(
    barcode: str,
    background_tasks: BackgroundTasks,
    item_id: str = Form(...),
    quantity: float = Form(1.0),
    unit_id: str = Form(""),
    db: Session = Depends(get_db),
):
    item = db.get(Item, item_id)
    if not item or item.source != "mealie":
        return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)

    _food_mapping(barcode, item, quantity, unit_id or None, db, mapped_by="manual")
    _resolve_notifications(barcode, db)
    db.commit()
    background_tasks.add_task(reconcile_linked_barcode, barcode)
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/create-and-map")
def barcode_create_and_map(
    barcode: str,
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    plural_name: str = Form(""),
    description: str = Form(""),
    label_id: str = Form(""),
    quantity: float = Form(1.0),
    unit_id: str = Form(""),
    db: Session = Depends(get_db),
):
    name = name.strip()
    if not name:
        return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)

    try:
        food = create_food(
            name=name,
            plural_name=plural_name.strip() or None,
            description=description.strip() or None,
            label_id=label_id or None,
        )
    except Exception:
        logger.exception("Failed to create Mealie Food for barcode %s", barcode)
        return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)

    aliases_raw = food.get("aliases") or []
    aliases = [a.get("name", a) if isinstance(a, dict) else a for a in aliases_raw]
    item = Item(
        id=food["id"],
        name=food.get("name") or name,
        source="mealie",
        aliases=json.dumps(aliases),
        synced_at=utcnow(),
    )
    db.merge(item)
    db.flush()
    item = db.get(Item, food["id"])

    _food_mapping(barcode, item, quantity, unit_id or None, db, mapped_by="manual")
    _resolve_notifications(barcode, db)
    db.commit()
    background_tasks.add_task(reconcile_linked_barcode, barcode)
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/map-recipe")
def barcode_map_recipe(
    barcode: str,
    background_tasks: BackgroundTasks,
    recipe_id: str = Form(...),
    recipe_name: str = Form(""),
    recipe_scale: float = Form(1.0),
    db: Session = Depends(get_db),
):
    recipe_id = recipe_id.strip()
    if not recipe_id:
        return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)

    _recipe_mapping(
        barcode,
        recipe_id,
        recipe_name.strip() or recipe_id,
        recipe_scale,
        db,
    )
    _resolve_notifications(barcode, db)
    db.commit()
    background_tasks.add_task(reconcile_linked_barcode, barcode)
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/mapping-settings")
def barcode_mapping_settings(
    barcode: str,
    quantity: float = Form(1.0),
    unit_id: str = Form(""),
    recipe_scale: float = Form(1.0),
    db: Session = Depends(get_db),
):
    mapping = db.get(BarcodeMapping, barcode)
    if mapping:
        if mapping.target_type == "food":
            mapping.quantity = max(quantity, 0.000001)
            mapping.unit_id = unit_id or None
        elif mapping.target_type == "recipe":
            mapping.recipe_scale = max(recipe_scale, 0.000001)
        db.commit()

    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/confirm")
def barcode_confirm(
    barcode: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    existing = db.get(BarcodeMapping, barcode)
    if existing and existing.mapped_by == "auto":
        existing.mapped_by = "auto_confirmed"
        _resolve_notifications(barcode, db)
        db.commit()
        background_tasks.add_task(reconcile_linked_barcode, barcode)
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/unmap")
def barcode_unmap(barcode: str, db: Session = Depends(get_db)):
    existing = db.get(BarcodeMapping, barcode)
    if existing:
        db.delete(existing)
        db.commit()
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/retry-lookup")
def barcode_retry_lookup(barcode: str, db: Session = Depends(get_db)):
    perform_lookup(barcode, db)
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/delete")
def barcode_delete(barcode: str, db: Session = Depends(get_db)):
    db.query(RetryQueue).filter(RetryQueue.barcode == barcode).delete()
    mapping = db.get(BarcodeMapping, barcode)
    if mapping:
        db.delete(mapping)
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

    words = [w for w in q.split() if len(w) >= 2] or [q]
    conditions = [Item.name.ilike(f"%{word}%") for word in words]
    items = (
        db.query(Item)
        .filter(Item.source == "mealie", or_(*conditions))
        .limit(20)
        .all()
    )
    return [{"id": i.id, "name": i.name, "source": i.source} for i in items]


@router.get("/recipes-search")
def recipes_search(q: str = Query(default="")):
    return search_recipes(q.strip(), limit=20)


@router.get("/api/barcodes")
def barcodes_api(status: str = "all", db: Session = Depends(get_db)):
    from app.templating import _localtime

    query = db.query(BarcodeCache).order_by(BarcodeCache.created_at.desc())
    mapped_sub = db.query(BarcodeMapping.barcode).subquery()

    if status == "mapped":
        query = query.filter(BarcodeCache.barcode.in_(mapped_sub))
    elif status == "pending":
        query = query.filter(
            BarcodeCache.found == True,
            ~BarcodeCache.barcode.in_(mapped_sub),
        )
    elif status == "unknown":
        query = query.filter(
            BarcodeCache.found == False,
            ~BarcodeCache.barcode.in_(mapped_sub),
        )

    barcodes_list = query.limit(200).all()
    mappings = {m.barcode: m for m in db.query(BarcodeMapping).all()}
    queued_barcodes = {r.barcode for r in db.query(RetryQueue).all()}

    result_items = []
    for bc in barcodes_list:
        mapping = mappings.get(bc.barcode)
        if mapping:
            bc_status = "mapped"
        elif bc.barcode in queued_barcodes:
            bc_status = "queued"
        elif not bc.found:
            bc_status = "unknown"
        else:
            bc_status = "pending"

        result_items.append({
            "barcode": bc.barcode,
            "title": bc.title or "—",
            "brand": bc.brand or "—",
            "source": bc.source or "—",
            "status": bc_status,
            "target_name": mapping.target_name if mapping else None,
            "target_id": mapping.target_id if mapping else None,
            "target_type": mapping.target_type if mapping else None,
            "mapped_by": mapping.mapped_by if mapping else None,
            "created_at": _localtime(bc.created_at),
        })

    return {"items": result_items}
