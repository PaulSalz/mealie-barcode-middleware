from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import BarcodeMapping, BarcodeTarget, Item
from app.services.mealie import get_food
from app.services.mealie_extras import cached_labels, cached_units, clear_catalog_cache
from app.utils import utcnow

logger = logging.getLogger(__name__)
router = APIRouter()

_http = httpx.Client(
    limits=httpx.Limits(max_connections=8, max_keepalive_connections=4, keepalive_expiry=60.0),
)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.mealie_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _normalize_substitutions(existing: dict) -> list[dict]:
    result = []
    for sub in existing.get("substitutions") or []:
        if not isinstance(sub, dict):
            continue
        substitute_id = sub.get("substituteFoodId")
        if not substitute_id and isinstance(sub.get("substituteFood"), dict):
            substitute_id = sub["substituteFood"].get("id")
        result.append({"substituteFoodId": substitute_id, "note": sub.get("note")})
    return result


def _food_unit(food: dict) -> tuple[str | None, str | None]:
    unit = food.get("unit")
    if isinstance(unit, dict):
        return food.get("unitId") or unit.get("id"), unit.get("name") or unit.get("abbreviation")
    return food.get("unitId"), None


def _food_label(food: dict) -> tuple[str | None, str | None]:
    label = food.get("label")
    if isinstance(label, dict):
        return label.get("id"), label.get("name")
    return food.get("labelId"), None


def _catalog_rows(rows: list[dict], *, unit: bool = False) -> list[dict]:
    result = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        entry = {"id": str(row["id"]), "name": row.get("name") or row.get("label") or str(row["id"])}
        if unit:
            entry["abbreviation"] = row.get("abbreviation") or ""
        result.append(entry)
    return result


class FoodTargetEdit(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    plural_name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    unit_id: str | None = Field(default=None, max_length=128)
    label_id: str | None = Field(default=None, max_length=128)


@router.get("/api/target-food-v6/{target_id}")
def get_target_food_v6(target_id: int, db: Session = Depends(get_db)):
    target = db.get(BarcodeTarget, target_id)
    if not target or target.target_type != "food":
        raise HTTPException(status_code=404, detail="Food target not found")
    item = db.get(Item, target.target_id)
    food = get_food(target.target_id)
    if not food:
        raise HTTPException(status_code=502, detail="Mealie Food could not be loaded")

    unit_id, _ = _food_unit(food)
    label_id, _ = _food_label(food)
    return {
        "target": {
            "id": target.id,
            "barcode": target.barcode,
            "quantity": target.quantity,
            "unit_id": target.unit_id,
        },
        "food": {
            "id": target.target_id,
            "name": food.get("name") or (item.name if item else target.target_name) or "",
            "plural_name": food.get("pluralName") or "",
            "description": food.get("description") or "",
            "unit_id": unit_id or (item.default_unit_id if item else None),
            "label_id": label_id or (item.label_id if item else None),
        },
        "units": _catalog_rows(cached_units(), unit=True),
        "labels": _catalog_rows(cached_labels()),
    }


@router.post("/api/target-food-v6/{target_id}")
def save_target_food_v6(target_id: int, body: FoodTargetEdit, db: Session = Depends(get_db)):
    target = db.get(BarcodeTarget, target_id)
    if not target or target.target_type != "food":
        raise HTTPException(status_code=404, detail="Food target not found")

    existing = get_food(target.target_id)
    if not existing:
        raise HTTPException(status_code=502, detail="Mealie Food could not be loaded")

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name is required")

    payload = {
        "id": existing.get("id"),
        "name": name,
        "pluralName": (body.plural_name or "").strip() or None,
        "description": body.description or "",
        "labelId": (body.label_id or "").strip() or None,
        "unitId": (body.unit_id or "").strip() or None,
        "aliases": existing.get("aliases") or [],
        "substitutions": _normalize_substitutions(existing),
        "householdsWithIngredientFood": existing.get("householdsWithIngredientFood") or [],
        "extras": existing.get("extras") or {},
    }

    try:
        response = _http.put(
            f"{settings.mealie_url.rstrip('/')}/api/foods/{target.target_id}",
            headers=_headers(),
            json=payload,
            timeout=httpx.Timeout(8.0, connect=1.5),
        )
    except httpx.HTTPError as exc:
        logger.warning("Food editor update failed for %s: %s", target.target_id, exc)
        raise HTTPException(status_code=502, detail="Mealie Food update failed") from exc

    if response.status_code not in (200, 201):
        logger.warning("Food editor update returned %s: %s", response.status_code, response.text[:300])
        raise HTTPException(status_code=502, detail=f"Mealie returned HTTP {response.status_code}")

    try:
        updated = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Mealie returned invalid JSON") from exc
    if not isinstance(updated, dict):
        raise HTTPException(status_code=502, detail="Mealie returned an invalid Food")

    item = db.get(Item, target.target_id)
    old_default_unit = item.default_unit_id if item else None
    unit_id, unit_name = _food_unit(updated)
    label_id, label_name = _food_label(updated)

    unit_lookup = {str(row.get("id")): row for row in cached_units() if isinstance(row, dict) and row.get("id")}
    label_lookup = {str(row.get("id")): row for row in cached_labels() if isinstance(row, dict) and row.get("id")}
    if unit_id and not unit_name:
        row = unit_lookup.get(str(unit_id), {})
        unit_name = row.get("name") or row.get("abbreviation")
    if label_id and not label_name:
        row = label_lookup.get(str(label_id), {})
        label_name = row.get("name")

    if item:
        item.name = updated.get("name") or name
        item.default_unit_id = unit_id
        item.default_unit_name = unit_name
        item.label_id = label_id
        item.label_name = label_name
        item.updated_at = utcnow()

    targets = db.query(BarcodeTarget).filter(
        BarcodeTarget.target_type == "food",
        BarcodeTarget.target_id == target.target_id,
    ).all()
    for row in targets:
        row.target_name = updated.get("name") or name
        if row.unit_id in {None, "", old_default_unit}:
            row.unit_id = unit_id

    mappings = db.query(BarcodeMapping).filter(
        BarcodeMapping.target_type == "food",
        BarcodeMapping.target_id == target.target_id,
    ).all()
    for row in mappings:
        row.target_name = updated.get("name") or name
        if row.unit_id in {None, "", old_default_unit}:
            row.unit_id = unit_id

    db.commit()
    clear_catalog_cache()
    return {
        "ok": True,
        "food": {
            "id": target.target_id,
            "name": updated.get("name") or name,
            "plural_name": updated.get("pluralName") or "",
            "description": updated.get("description") or "",
            "unit_id": unit_id,
            "label_id": label_id,
        },
    }
