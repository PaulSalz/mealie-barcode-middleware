from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BarcodeCache, BarcodeMapping, BarcodeTarget, Item
from app.services.barcode_lookup import perform_lookup
from app.services.fuzzy import fuzzy_match
from app.services.mealie_extras import cached_units
from app.services.shopping import (
    get_default_shopping_list_id,
    get_preferred_unit_for_food,
    get_shopping_lists,
)
from app.services.targets import get_barcode_targets, sync_primary_target

router = APIRouter()


class TargetPayload(BaseModel):
    barcode: str | None = None
    target_type: str = "food"
    target_id: str
    target_name: str | None = None
    quantity: float | None = None
    unit_id: str | None = None
    recipe_scale: float = 1.0
    destination_type: str = "mealie"
    shopping_list_id: str | None = None
    endpoint_url: str | None = None
    enabled: bool = True


class PrimarySettingsPayload(BaseModel):
    quantity: float | None = None
    unit_id: str | None = None
    recipe_scale: float | None = None
    shopping_list_id: str | None = None


class MetadataPayload(BaseModel):
    title: str = ""
    brand: str = ""


class LookupPayload(BaseModel):
    barcode: str
    clear_overrides: bool = False


def _target_json(target: BarcodeTarget, db: Session) -> dict:
    preferred = get_preferred_unit_for_food(target.target_id) if target.target_type == "food" else None
    lists = {str(row["id"]): row["name"] for row in get_shopping_lists()}
    default_id = get_default_shopping_list_id()
    list_id = target.shopping_list_id or default_id
    unit_name = next((row.get("name") or row.get("abbreviation") for row in cached_units() if str(row.get("id")) == str(target.unit_id)), None)
    return {
        "id": target.id,
        "barcode": target.barcode,
        "primary": target.is_primary,
        "enabled": target.enabled,
        "target_type": target.target_type,
        "target_id": target.target_id,
        "target_name": target.target_name or target.target_id,
        "quantity": target.quantity,
        "unit_id": target.unit_id,
        "unit_name": unit_name,
        "recipe_scale": target.recipe_scale,
        "destination_type": target.destination_type,
        "shopping_list_id": list_id,
        "shopping_list_name": lists.get(str(list_id)) if list_id else None,
        "shopping_list_default": bool(list_id and str(list_id) == str(default_id)),
        "endpoint_url": target.endpoint_url,
        "preferred_unit": preferred,
        "unit_mismatch": bool(preferred and target.unit_id and str(target.unit_id) != str(preferred.get("id"))),
    }


def _validated_target(payload: TargetPayload, db: Session) -> tuple[str, str, str | None]:
    target_type = payload.target_type.strip().lower()
    if target_type not in {"food", "recipe"}:
        raise ValueError("Target type must be food or recipe")
    destination = payload.destination_type.strip().lower()
    if destination not in {"inherit", "mealie", "homeassistant", "webhook"}:
        raise ValueError("Destination must be inherit, mealie, homeassistant or webhook")
    target_id = payload.target_id.strip()
    if not target_id:
        raise ValueError("Target ID is required")
    if target_type == "food":
        item = db.get(Item, target_id)
        if not item:
            raise ValueError("Food does not exist in the local Mealie catalog")
        target_name = item.name
    else:
        target_name = (payload.target_name or target_id).strip()
    if destination == "webhook":
        endpoint = (payload.endpoint_url or "").strip()
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Webhook endpoint must be a valid http:// or https:// URL")
    if payload.shopping_list_id:
        valid_ids = {str(row["id"]) for row in get_shopping_lists()}
        if str(payload.shopping_list_id) not in valid_ids:
            raise ValueError("Selected shopping list no longer exists")
    return target_type, destination, target_name


@router.get("/api/barcode-targets")
def barcode_targets(barcode: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    rows = get_barcode_targets(db, barcode, enabled_only=False)
    return {
        "barcode": barcode,
        "default_list_id": get_default_shopping_list_id(),
        "shopping_lists": get_shopping_lists(),
        "units": [
            {"id": str(row.get("id")), "name": row.get("name") or row.get("abbreviation") or "Unit"}
            for row in cached_units() if row.get("id")
        ],
        "targets": [_target_json(row, db) for row in rows],
    }


@router.post("/api/barcode-targets")
def add_barcode_target(payload: TargetPayload, db: Session = Depends(get_db)):
    barcode = (payload.barcode or "").strip()
    if not barcode:
        return JSONResponse({"error": "Barcode is required"}, status_code=400)
    if not db.get(BarcodeCache, barcode):
        return JSONResponse({"error": "Barcode does not exist"}, status_code=404)
    try:
        target_type, destination, target_name = _validated_target(payload, db)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    quantity = payload.quantity
    if quantity is not None and quantity <= 0:
        quantity = None
    row = BarcodeTarget(
        barcode=barcode,
        is_primary=False,
        enabled=payload.enabled,
        target_type=target_type,
        target_id=payload.target_id.strip(),
        target_name=target_name,
        quantity=quantity if target_type == "food" else None,
        unit_id=(payload.unit_id or None) if target_type == "food" else None,
        recipe_scale=max(float(payload.recipe_scale or 1.0), 0.001),
        destination_type=destination,
        shopping_list_id=(payload.shopping_list_id or None),
        endpoint_url=(payload.endpoint_url or "").strip() or None,
        mapped_by="manual",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "target": _target_json(row, db)}


@router.patch("/api/barcode-targets/{target_id}")
def update_barcode_target(target_id: int, payload: TargetPayload, db: Session = Depends(get_db)):
    row = db.get(BarcodeTarget, target_id)
    if not row:
        return JSONResponse({"error": "Target not found"}, status_code=404)
    if row.is_primary:
        return JSONResponse({"error": "Primary target is edited in the Current target card"}, status_code=409)
    try:
        target_type, destination, target_name = _validated_target(payload, db)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    quantity = payload.quantity
    if quantity is not None and quantity <= 0:
        quantity = None
    row.enabled = payload.enabled
    row.target_type = target_type
    row.target_id = payload.target_id.strip()
    row.target_name = target_name
    row.quantity = quantity if target_type == "food" else None
    row.unit_id = (payload.unit_id or None) if target_type == "food" else None
    row.recipe_scale = max(float(payload.recipe_scale or 1.0), 0.001)
    row.destination_type = destination
    row.shopping_list_id = payload.shopping_list_id or None
    row.endpoint_url = (payload.endpoint_url or "").strip() or None
    db.commit()
    return {"ok": True, "target": _target_json(row, db)}


@router.delete("/api/barcode-targets/{target_id}")
def delete_barcode_target(target_id: int, db: Session = Depends(get_db)):
    row = db.get(BarcodeTarget, target_id)
    if not row:
        return JSONResponse({"error": "Target not found"}, status_code=404)
    if row.is_primary:
        return JSONResponse({"error": "Use Unlink to remove the primary target"}, status_code=409)
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.put("/api/barcodes/{barcode:path}/primary-target")
def save_primary_target_settings(barcode: str, payload: PrimarySettingsPayload, db: Session = Depends(get_db)):
    mapping = db.get(BarcodeMapping, barcode)
    if not mapping:
        return JSONResponse({"error": "Primary target not found"}, status_code=404)
    if mapping.target_type == "food":
        quantity = payload.quantity
        mapping.quantity = 0.001 if quantity is None or quantity <= 0 else round(float(quantity), 3)
        mapping.unit_id = (payload.unit_id or "").strip() or None
    elif mapping.target_type == "recipe":
        mapping.recipe_scale = max(round(float(payload.recipe_scale or 1.0), 3), 0.001)
        list_id = (payload.shopping_list_id or "").strip() or None
        if list_id:
            valid = {str(row["id"]) for row in get_shopping_lists()}
            if list_id not in valid:
                return JSONResponse({"error": "Selected shopping list no longer exists"}, status_code=400)
        mapping.shopping_list_id = list_id
    db.commit()
    primary = sync_primary_target(db, barcode)
    db.commit()
    return {"ok": True, "target": _target_json(primary, db) if primary else None}


@router.get("/api/foods/search")
def ranked_food_search(q: str = Query(""), limit: int = Query(6, ge=1, le=20), db: Session = Depends(get_db)):
    q = q.strip()
    if not q:
        return {"items": []}
    rows = fuzzy_match(q, None, db)[:limit]
    return {"items": [
        {
            "id": row["item_id"],
            "name": row["item_name"],
            "score": row["score"],
            "exact": bool(row.get("exact")),
            "prefix": bool(row.get("prefix")),
        }
        for row in rows
    ]}


@router.put("/api/barcodes/{barcode:path}/metadata")
def save_barcode_metadata(barcode: str, payload: MetadataPayload, db: Session = Depends(get_db)):
    cached = db.get(BarcodeCache, barcode)
    if not cached:
        return JSONResponse({"error": "Barcode not found"}, status_code=404)
    cached.custom_title = payload.title.strip() or None
    cached.custom_brand = payload.brand.strip() or None
    db.commit()
    return {
        "ok": True,
        "title": cached.display_title,
        "brand": cached.display_brand,
        "custom_title": cached.custom_title,
        "custom_brand": cached.custom_brand,
    }


@router.post("/api/barcode-lookup")
def redo_barcode_lookup(payload: LookupPayload, db: Session = Depends(get_db)):
    barcode = payload.barcode.strip()
    cached = db.get(BarcodeCache, barcode)
    if not cached:
        return JSONResponse({"error": "Barcode not found"}, status_code=404)
    if not barcode.isdigit():
        return JSONResponse({"error": "External product lookup is only available for numeric product barcodes"}, status_code=400)
    if payload.clear_overrides:
        cached.custom_title = None
        cached.custom_brand = None
        db.commit()
    refreshed = perform_lookup(barcode, db)
    return {
        "ok": True,
        "found": refreshed.found,
        "title": refreshed.display_title,
        "brand": refreshed.display_brand,
        "source": refreshed.source,
        "quantity": refreshed.quantity,
        "overrides_cleared": payload.clear_overrides,
    }
