from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import BarcodeMapping, BarcodeTarget


def _mapping_quantity(mapping: BarcodeMapping) -> float | None:
    value = mapping.quantity
    return None if value is None or value <= 0.001 else value


def sync_primary_target(db: Session, barcode: str) -> BarcodeTarget | None:
    """Keep the mirrored primary target consistent with BarcodeMapping.

    BarcodeMapping remains the backwards-compatible primary mapping. Additional
    independently-routed targets use BarcodeTarget rows with is_primary=False.
    """
    mapping = db.get(BarcodeMapping, barcode)
    primary = (
        db.query(BarcodeTarget)
        .filter(BarcodeTarget.barcode == barcode, BarcodeTarget.is_primary == True)
        .order_by(BarcodeTarget.id)
        .first()
    )
    if not mapping:
        if primary:
            db.delete(primary)
            db.flush()
        return None

    if not primary:
        primary = BarcodeTarget(
            barcode=barcode,
            is_primary=True,
            enabled=True,
            target_type=mapping.target_type,
            target_id=mapping.target_id,
        )
        db.add(primary)

    primary.enabled = True
    primary.target_type = mapping.target_type
    primary.target_id = mapping.target_id
    primary.target_name = mapping.target_name
    primary.quantity = _mapping_quantity(mapping) if mapping.target_type == "food" else None
    primary.unit_id = mapping.unit_id if mapping.target_type == "food" else None
    primary.recipe_scale = mapping.recipe_scale or 1.0
    primary.destination_type = "inherit"
    primary.shopping_list_id = mapping.shopping_list_id or None
    primary.endpoint_url = None
    primary.mapped_by = mapping.mapped_by or "manual"
    db.flush()
    return primary


def get_barcode_targets(db: Session, barcode: str, *, enabled_only: bool = True) -> list[BarcodeTarget]:
    sync_primary_target(db, barcode)
    query = db.query(BarcodeTarget).filter(BarcodeTarget.barcode == barcode)
    if enabled_only:
        query = query.filter(BarcodeTarget.enabled == True)
    return query.order_by(BarcodeTarget.is_primary.desc(), BarcodeTarget.id.asc()).all()


def delete_barcode_targets(db: Session, barcode: str) -> int:
    return db.query(BarcodeTarget).filter(BarcodeTarget.barcode == barcode).delete(synchronize_session=False)


def target_summary(targets: list[BarcodeTarget]) -> str:
    names: list[str] = []
    for target in targets:
        name = target.target_name or target.target_id
        if name and name not in names:
            names.append(name)
    if not names:
        return f"{len(targets)} targets"
    if len(names) <= 2:
        return " + ".join(names)
    return f"{names[0]} + {len(names) - 1} more"
