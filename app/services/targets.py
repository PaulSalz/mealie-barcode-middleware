import json

from app.models import BarcodeTarget


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
    """Return canonical targets for a barcode.

    Legacy BarcodeMapping rows are migrated forward during database startup. Runtime
    code deliberately never falls back to or recreates that compatibility table,
    keeping BarcodeTarget as the only source of truth after initialization.
    """
    return (
        db.query(BarcodeTarget)
        .filter(BarcodeTarget.barcode == barcode)
        .order_by(BarcodeTarget.position, BarcodeTarget.id)
        .all()
    )


def primary_target(barcode: str, db, *, enabled_only: bool = True) -> BarcodeTarget | None:
    query = db.query(BarcodeTarget).filter(BarcodeTarget.barcode == barcode)
    if enabled_only:
        query = query.filter(BarcodeTarget.enabled == True)
    return query.order_by(BarcodeTarget.position, BarcodeTarget.id).first()


def primary_targets_by_barcode(db, barcodes: list[str] | None = None) -> dict[str, BarcodeTarget]:
    query = db.query(BarcodeTarget).filter(BarcodeTarget.enabled == True)
    if barcodes is not None:
        if not barcodes:
            return {}
        query = query.filter(BarcodeTarget.barcode.in_(barcodes))
    rows = query.order_by(BarcodeTarget.barcode, BarcodeTarget.position, BarcodeTarget.id).all()
    result: dict[str, BarcodeTarget] = {}
    for row in rows:
        result.setdefault(row.barcode, row)
    return result


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

    BarcodeTarget is the canonical mapping store. A Food/recipe already attached
    to the barcode is updated in place instead of creating another identical row.
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
    return target
