import logging
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import (
    BarcodeCache,
    BarcodeMapping,
    RecipeBarcodeMapping,
    Item,
    Activity,
    RetryQueue,
)
from app.services.barcode_lookup import perform_lookup
from app.services.fuzzy import fuzzy_match
from app.services.homeassistant import dismiss_notification as ha_dismiss
from app.services.mealie import (
    reconcile_linked_barcode,
    create_food,
    upsert_local_food,
    get_units,
    get_food_labels,
    get_recipes,
    get_recipe,
    add_recipe_to_shopping_list,
)
from app.services.shopping_cleanup import delete_shopping_item
from app.templating import templates

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


def _all_mapped_barcodes(db: Session) -> set[str]:
    food = {m.barcode for m in db.query(BarcodeMapping.barcode).all()}
    recipes = {m.barcode for m in db.query(RecipeBarcodeMapping.barcode).all()}
    return food | recipes


def _normalise_unit_id(unit_id: str | None) -> str | None:
    value = (unit_id or "").strip()
    return value or None


def _normalise_quantity(quantity: float) -> float:
    return quantity if quantity > 0 else 1.0


@router.get("/barcodes", response_class=HTMLResponse)
def barcodes_list(
    request: Request,
    status: str = Query(default="all"),
    db: Session = Depends(get_db),
):
    query = db.query(BarcodeCache).order_by(BarcodeCache.created_at.desc())
    mapped_ids = _all_mapped_barcodes(db)

    if status == "mapped":
        if mapped_ids:
            query = query.filter(BarcodeCache.barcode.in_(mapped_ids))
        else:
            query = query.filter(False)
    elif status == "pending":
        query = query.filter(BarcodeCache.found == True)
        if mapped_ids:
            query = query.filter(~BarcodeCache.barcode.in_(mapped_ids))
    elif status == "unknown":
        query = query.filter(BarcodeCache.found == False)
        if mapped_ids:
            query = query.filter(~BarcodeCache.barcode.in_(mapped_ids))

    barcodes = query.all()

    mappings = {m.barcode: m for m in db.query(BarcodeMapping).all()}
    recipe_mappings = {m.barcode: m for m in db.query(RecipeBarcodeMapping).all()}
    queued_barcodes = {r.barcode for r in db.query(RetryQueue).all()}
    item_ids = [m.item_id for m in mappings.values()]
    items_map = {i.id: i for i in db.query(Item).filter(Item.id.in_(item_ids)).all()} if item_ids else {}

    items = []
    for bc in barcodes:
        mapping = mappings.get(bc.barcode)
        recipe_mapping = recipe_mappings.get(bc.barcode)
        item = items_map.get(mapping.item_id) if mapping else None
        if mapping or recipe_mapping:
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
            "recipe_mapping": recipe_mapping,
            "item": item,
            "linked_name": (
                item.name if item else
                (recipe_mapping.recipe_name or recipe_mapping.recipe_id if recipe_mapping else None)
            ),
            "linked_type": "recipe" if recipe_mapping else ("food" if mapping else None),
            "status": bc_status,
        })

    return templates.TemplateResponse(request, "barcodes.html", {
        "items": items,
        "current_status": status,
    })


@router.get("/barcodes/{barcode:path}", response_class=HTMLResponse)
def barcode_detail(
    request: Request,
    barcode: str,
    db: Session = Depends(get_db),
):
    cached = db.get(BarcodeCache, barcode)
    mapping = db.get(BarcodeMapping, barcode)
    recipe_mapping = db.get(RecipeBarcodeMapping, barcode)
    mapped_item = db.get(Item, mapping.item_id) if mapping else None

    _mark_notifications_read(barcode, db)
    db.commit()

    candidates = []
    if cached and cached.title:
        candidates = fuzzy_match(cached.title, cached.brand, db)[:10]

    mapped_barcodes = _all_mapped_barcodes(db)
    next_query = db.query(BarcodeCache).filter(BarcodeCache.barcode != barcode)
    if mapped_barcodes:
        next_query = next_query.filter(~BarcodeCache.barcode.in_(mapped_barcodes))
    next_unmapped = next_query.order_by(BarcodeCache.created_at.desc()).first()

    is_confirmed = bool(mapping and mapping.mapped_by in ("manual", "auto_confirmed"))

    return templates.TemplateResponse(request, "barcode_detail.html", {
        "cached": cached,
        "mapping": mapping,
        "recipe_mapping": recipe_mapping,
        "mapped_item": mapped_item,
        "is_confirmed": is_confirmed,
        "candidates": candidates,
        "next_unmapped": next_unmapped,
        "threshold": settings.fuzzy_match_threshold,
        "units": get_units(),
        "food_labels": get_food_labels(),
        "recipes": get_recipes(),
    })


@router.post("/barcodes/{barcode:path}/map")
def barcode_map(
    barcode: str,
    background_tasks: BackgroundTasks,
    item_id: str = Form(...),
    quantity: float = Form(1.0),
    unit_id: str = Form(""),
    db: Session = Depends(get_db),
):
    quantity = _normalise_quantity(quantity)
    unit_id_value = _normalise_unit_id(unit_id)

    recipe_mapping = db.get(RecipeBarcodeMapping, barcode)
    if recipe_mapping:
        db.delete(recipe_mapping)

    existing = db.get(BarcodeMapping, barcode)
    if existing:
        existing.item_id = item_id
        existing.quantity = quantity
        existing.unit_id = unit_id_value
        existing.mapped_by = "manual"
    else:
        db.add(BarcodeMapping(
            barcode=barcode,
            item_id=item_id,
            quantity=quantity,
            unit_id=unit_id_value,
            mapped_by="manual",
        ))

    _resolve_notifications(barcode, db)
    db.commit()
    background_tasks.add_task(reconcile_linked_barcode, barcode)
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/mapping-settings")
def barcode_mapping_settings(
    barcode: str,
    background_tasks: BackgroundTasks,
    quantity: float = Form(1.0),
    unit_id: str = Form(""),
    db: Session = Depends(get_db),
):
    mapping = db.get(BarcodeMapping, barcode)
    if mapping:
        mapping.quantity = _normalise_quantity(quantity)
        mapping.unit_id = _normalise_unit_id(unit_id)
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
    """Create a real Mealie food, then map the barcode to its food ID."""
    name = name.strip()
    if not name:
        return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)

    try:
        food = create_food(
            name=name,
            plural_name=plural_name.strip() or None,
            description=description.strip() or None,
            label_id=label_id.strip() or None,
        )
    except Exception as exc:
        logger.exception("Failed to create Mealie food for barcode %s", barcode)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    item = upsert_local_food(food, db)

    recipe_mapping = db.get(RecipeBarcodeMapping, barcode)
    if recipe_mapping:
        db.delete(recipe_mapping)

    existing = db.get(BarcodeMapping, barcode)
    if existing:
        existing.item_id = item.id
        existing.quantity = _normalise_quantity(quantity)
        existing.unit_id = _normalise_unit_id(unit_id)
        existing.mapped_by = "manual"
    else:
        db.add(BarcodeMapping(
            barcode=barcode,
            item_id=item.id,
            quantity=_normalise_quantity(quantity),
            unit_id=_normalise_unit_id(unit_id),
            mapped_by="manual",
        ))

    _resolve_notifications(barcode, db)
    db.commit()
    background_tasks.add_task(reconcile_linked_barcode, barcode)
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/map-recipe")
def barcode_map_recipe(
    barcode: str,
    recipe_id: str = Form(...),
    recipe_scale: float = Form(1.0),
    db: Session = Depends(get_db),
):
    """Map a barcode to a Mealie recipe ID for native recipe-list linking."""
    recipe_id = recipe_id.strip()
    if not recipe_id:
        return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)

    scale = _normalise_quantity(recipe_scale)
    recipe = get_recipe(recipe_id)
    recipe_name = recipe.get("name") if recipe else recipe_id

    food_mapping = db.get(BarcodeMapping, barcode)
    if food_mapping:
        db.delete(food_mapping)

    existing = db.get(RecipeBarcodeMapping, barcode)
    is_new_mapping = existing is None
    if existing:
        existing.recipe_id = recipe_id
        existing.recipe_name = recipe_name
        existing.recipe_scale = scale
        existing.mapped_by = "manual"
    else:
        db.add(RecipeBarcodeMapping(
            barcode=barcode,
            recipe_id=recipe_id,
            recipe_name=recipe_name,
            recipe_scale=scale,
            mapped_by="manual",
        ))

    # If this mapping resolves a scan that was already added as a text note,
    # fulfil that scan immediately with Mealie's native recipe reference and
    # remove the temporary note only after the recipe add succeeded.
    cached = db.get(BarcodeCache, barcode)
    if is_new_mapping:
        added = add_recipe_to_shopping_list(recipe_id, scale)
        if added and cached and cached.shopping_item_id:
            if delete_shopping_item(cached.shopping_item_id):
                cached.shopping_item_id = None

    _resolve_notifications(barcode, db)
    db.commit()
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/recipe-settings")
def barcode_recipe_settings(
    barcode: str,
    recipe_scale: float = Form(1.0),
    db: Session = Depends(get_db),
):
    mapping = db.get(RecipeBarcodeMapping, barcode)
    if mapping:
        mapping.recipe_scale = _normalise_quantity(recipe_scale)
        db.commit()
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/confirm")
def barcode_confirm(barcode: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    existing = db.get(BarcodeMapping, barcode)
    if existing and existing.mapped_by == "auto":
        existing.mapped_by = "auto_confirmed"
        _resolve_notifications(barcode, db)
        db.commit()
        background_tasks.add_task(reconcile_linked_barcode, barcode)
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/unmap")
def barcode_unmap(barcode: str, db: Session = Depends(get_db)):
    food_mapping = db.get(BarcodeMapping, barcode)
    recipe_mapping = db.get(RecipeBarcodeMapping, barcode)
    if food_mapping:
        db.delete(food_mapping)
    if recipe_mapping:
        db.delete(recipe_mapping)
    if food_mapping or recipe_mapping:
        db.commit()
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/retry-lookup")
def barcode_retry_lookup(barcode: str, db: Session = Depends(get_db)):
    perform_lookup(barcode, db)
    return RedirectResponse(f"/barcodes/{quote(barcode, safe='')}", status_code=303)


@router.post("/barcodes/{barcode:path}/delete")
def barcode_delete(barcode: str, db: Session = Depends(get_db)):
    db.query(RetryQueue).filter(RetryQueue.barcode == barcode).delete()
    food_mapping = db.get(BarcodeMapping, barcode)
    recipe_mapping = db.get(RecipeBarcodeMapping, barcode)
    if food_mapping:
        db.delete(food_mapping)
    if recipe_mapping:
        db.delete(recipe_mapping)
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
    words = [w for w in q.split() if len(w) >= 2]
    if not words:
        words = [q]
    conditions = [Item.name.ilike(f"%{word}%") for word in words]
    items = db.query(Item).filter(or_(*conditions)).limit(20).all()
    return [{"id": i.id, "name": i.name, "source": i.source} for i in items]


@router.get("/api/barcodes")
def barcodes_api(status: str = "all", db: Session = Depends(get_db)):
    from app.templating import _localtime

    query = db.query(BarcodeCache).order_by(BarcodeCache.created_at.desc())
    mapped_ids = _all_mapped_barcodes(db)

    if status == "mapped":
        if mapped_ids:
            query = query.filter(BarcodeCache.barcode.in_(mapped_ids))
        else:
            query = query.filter(False)
    elif status == "pending":
        query = query.filter(BarcodeCache.found == True)
        if mapped_ids:
            query = query.filter(~BarcodeCache.barcode.in_(mapped_ids))
    elif status == "unknown":
        query = query.filter(BarcodeCache.found == False)
        if mapped_ids:
            query = query.filter(~BarcodeCache.barcode.in_(mapped_ids))

    barcodes_list = query.limit(200).all()

    mappings = {m.barcode: m for m in db.query(BarcodeMapping).all()}
    recipe_mappings = {m.barcode: m for m in db.query(RecipeBarcodeMapping).all()}
    queued_barcodes = {r.barcode for r in db.query(RetryQueue).all()}
    item_ids = [m.item_id for m in mappings.values()]
    items_map = {i.id: i for i in db.query(Item).filter(Item.id.in_(item_ids)).all()} if item_ids else {}

    result_items = []
    for bc in barcodes_list:
        mapping = mappings.get(bc.barcode)
        recipe_mapping = recipe_mappings.get(bc.barcode)
        item = items_map.get(mapping.item_id) if mapping else None
        if mapping or recipe_mapping:
            bc_status = "mapped"
        elif bc.barcode in queued_barcodes:
            bc_status = "queued"
        elif not bc.found:
            bc_status = "unknown"
        else:
            bc_status = "pending"
        linked_name = item.name if item else (
            recipe_mapping.recipe_name or recipe_mapping.recipe_id if recipe_mapping else None
        )
        result_items.append({
            "barcode": bc.barcode,
            "title": bc.title or "—",
            "brand": bc.brand or "—",
            "source": bc.source or "—",
            "status": bc_status,
            "item_name": linked_name,
            "item_id": item.id if item else None,
            "mapped_by": mapping.mapped_by if mapping else (recipe_mapping.mapped_by if recipe_mapping else None),
            "linked_type": "recipe" if recipe_mapping else ("food" if mapping else None),
            "created_at": _localtime(bc.created_at),
        })

    return {"items": result_items}
