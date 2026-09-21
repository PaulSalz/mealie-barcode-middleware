import json

from app.models import BarcodeMapping, BarcodeTarget


def list_ids(target: BarcodeTarget) -> list[str]:
    try:
        values = json.loads(target.shopping_list_ids_json or "[]")
    except (TypeError, ValueError):
        return []
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def set_list_ids(target: BarcodeTarget, values) -> None:
    target.shopping_list_ids_json = json.dumps(
        list(dict.fromkeys(str(value).strip() for value in (values or []) if str(value).strip()))
    )


def ensure_targets(barcode: str, db) -> list[BarcodeTarget]:
    targets = (
        db.query(BarcodeTarget)
        .filter(BarcodeTarget.barcode == barcode)
        .order_by(BarcodeTarget.position, BarcodeTarget.id)
        .all()
    )
    if targets:
        return targets
    mapping = db.get(BarcodeMapping, barcode)
    if not mapping:
        return []
    target = BarcodeTarget(
        barcode=barcode,
        target_type=mapping.target_type,
        target_id=mapping.target_id,
        target_name=mapping.target_name,
        route="inherit",
        quantity=None if mapping.target_type == "food" and mapping.quantity <= 0.001 else mapping.quantity,
        unit_id=mapping.unit_id,
        recipe_scale=mapping.recipe_scale or 1.0,
        position=0,
        enabled=True,
        mapped_by=mapping.mapped_by,
    )
    set_list_ids(target, [mapping.shopping_list_id] if mapping.shopping_list_id else [])
    db.add(target)
    db.commit()
    db.refresh(target)
    return [target]


def sync_legacy_primary(barcode: str, db) -> None:
    """Mirror the first enabled target into BarcodeMapping for old clients/views."""
    target = (
        db.query(BarcodeTarget)
        .filter(BarcodeTarget.barcode == barcode, BarcodeTarget.enabled == True)
        .order_by(BarcodeTarget.position, BarcodeTarget.id)
        .first()
    )
    mapping = db.get(BarcodeMapping, barcode)
    if not target:
        if mapping:
            db.delete(mapping)
            db.commit()
        return
    if not mapping:
        mapping = BarcodeMapping(barcode=barcode, target_type=target.target_type, target_id=target.target_id)
        db.add(mapping)
    mapping.target_type = target.target_type
    mapping.target_id = target.target_id
    mapping.target_name = target.target_name
    mapping.quantity = target.quantity if target.quantity is not None else 0.001
    mapping.unit_id = target.unit_id
    mapping.recipe_scale = target.recipe_scale or 1.0
    ids = list_ids(target)
    mapping.shopping_list_id = ids[0] if ids else None
    mapping.mapped_by = target.mapped_by or "manual"
    db.commit()


def add_target(
    barcode: str,
    target_type: str,
    target_id: str,
    target_name: str,
    db,
    *,
    route: str = "inherit",
    list_ids_value=None,
    quantity: float | None = 1.0,
    unit_id: str | None = None,
    recipe_scale: float = 1.0,
    mapped_by: str = "manual",
) -> BarcodeTarget:
    """Add or update one logical target for a barcode.

    A Food/recipe already attached to the barcode is updated in place instead of
    creating another identical row. This makes repeated UI submissions safe and
    avoids position races from producing duplicate targets.
    """
    normalized_route = route if route in {"inherit", "mealie", "homeassistant", "both", "none"} else "inherit"
    existing_target = (
        db.query(BarcodeTarget)
        .filter(
            BarcodeTarget.barcode == barcode,
            BarcodeTarget.target_type == target_type,
            BarcodeTarget.target_id == target_id,
        )
        .order_by(BarcodeTarget.id)
        .first()
    )
    if existing_target:
        existing_target.target_name = target_name
        existing_target.route = normalized_route
        existing_target.quantity = quantity
        existing_target.unit_id = unit_id or None
        existing_target.recipe_scale = recipe_scale or 1.0
        existing_target.enabled = True
        existing_target.mapped_by = mapped_by or existing_target.mapped_by or "manual"
        set_list_ids(existing_target, list_ids_value or [])
        db.commit()
        db.refresh(existing_target)
        sync_legacy_primary(barcode, db)
        return existing_target

    existing = ensure_targets(barcode, db)
    positions = [row.position for row in existing if isinstance(row.position, int)]
    position = max(positions, default=-1) + 1
    target = BarcodeTarget(
        barcode=barcode,
        target_type=target_type,
        target_id=target_id,
        target_name=target_name,
        route=normalized_route,
        quantity=quantity,
        unit_id=unit_id or None,
        recipe_scale=recipe_scale or 1.0,
        position=position,
        enabled=True,
        mapped_by=mapped_by,
    )
    set_list_ids(target, list_ids_value or [])
    db.add(target)
    db.commit()
    db.refresh(target)
    sync_legacy_primary(barcode, db)
    return target
