from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Activity, BarcodeCache, BarcodeTarget
from app.utils import utcnow


def has_local_barcode_state(barcode: str, db: Session) -> bool:
    """Return whether B2M has any durable local state for this barcode."""
    if db.query(BarcodeTarget.id).filter(BarcodeTarget.barcode == barcode).first():
        return True
    return db.query(Activity.id).filter(Activity.barcode == barcode).first() is not None


def has_routable_barcode_state(barcode: str, db: Session) -> bool:
    """Return whether the barcode has at least one enabled canonical target."""
    return db.query(BarcodeTarget.id).filter(
        BarcodeTarget.barcode == barcode,
        BarcodeTarget.enabled == True,
    ).first() is not None


def drop_stale_lookup_shell(barcode: str, db: Session) -> None:
    """Remove legacy recovery shells that never represented a provider lookup."""
    if not barcode.isdigit() or has_routable_barcode_state(barcode, db):
        return
    cached = db.get(BarcodeCache, barcode)
    if not cached:
        return
    if cached.source == "scan" and not cached.found and cached.lookup_attempted_at is None:
        db.delete(cached)
        db.commit()


def ensure_cache_shell(barcode: str, db: Session, *, only_if_known: bool = False) -> BarcodeCache | None:
    """Restore local cache identity without doing an external product lookup."""
    cached = db.get(BarcodeCache, barcode)
    if cached:
        return cached
    if only_if_known and not has_local_barcode_state(barcode, db):
        return None

    cached = BarcodeCache(
        barcode=barcode,
        source="action" if barcode.upper().startswith("ACTION:") else "scan",
        found=False,
        lookup_attempted_at=None,
        created_at=utcnow(),
    )
    db.add(cached)
    try:
        db.commit()
        db.refresh(cached)
        return cached
    except IntegrityError:
        # Scanner receipt and scan processing may rebuild the same identity at
        # nearly the same time. Keep whichever transaction won the race.
        db.rollback()
        return db.get(BarcodeCache, barcode)
