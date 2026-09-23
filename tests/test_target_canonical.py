from app.database import SessionLocal, init_db
from app.models import BarcodeCache, BarcodeMapping, BarcodeTarget, Item
from app.routers.scan import _handle_generic
from app.services.fuzzy import try_auto_map


def _cleanup(db, barcode: str, item_id: str) -> None:
    db.query(BarcodeTarget).filter(BarcodeTarget.barcode == barcode).delete(synchronize_session=False)
    mapping = db.get(BarcodeMapping, barcode)
    if mapping:
        db.delete(mapping)
    cached = db.get(BarcodeCache, barcode)
    if cached:
        db.delete(cached)
    item = db.get(Item, item_id)
    if item:
        db.delete(item)
    db.commit()


def test_fuzzy_auto_map_writes_only_barcode_target():
    init_db()
    barcode = "ci-target-auto-001"
    item_id = "ci-target-food-auto"
    db = SessionLocal()
    try:
        _cleanup(db, barcode, item_id)
        db.add(Item(id=item_id, name="Canonical Tomato", source="mealie"))
        db.commit()

        resolved = try_auto_map(barcode, "Canonical Tomato", None, db)
        assert resolved == item_id
        targets = db.query(BarcodeTarget).filter(BarcodeTarget.barcode == barcode).all()
        assert len(targets) == 1
        assert targets[0].target_id == item_id
        assert targets[0].mapped_by == "auto"
        assert db.get(BarcodeMapping, barcode) is None
    finally:
        _cleanup(db, barcode, item_id)
        db.close()


def test_generic_scan_writes_only_barcode_target():
    init_db()
    barcode = "GENERIC:Canonical%20Cucumber"
    item_id = "ci-target-food-generic"
    db = SessionLocal()
    try:
        _cleanup(db, barcode, item_id)
        db.add(Item(id=item_id, name="Canonical Cucumber", source="mealie"))
        db.commit()

        response = _handle_generic("Canonical Cucumber", barcode, db, paused=True)
        assert response.result == "added"
        targets = db.query(BarcodeTarget).filter(BarcodeTarget.barcode == barcode).all()
        assert len(targets) == 1
        assert targets[0].target_id == item_id
        assert targets[0].mapped_by == "generic"
        assert db.get(BarcodeMapping, barcode) is None
    finally:
        _cleanup(db, barcode, item_id)
        db.close()
