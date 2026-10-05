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


def test_barcode_map_imports_live_mealie_food_missing_from_local_cache(monkeypatch):
    from fastapi import BackgroundTasks

    from app.routers import barcodes

    init_db()
    barcode = "ci-barcode-live-food-search"
    item_id = "ci-food-live-search"
    db = SessionLocal()
    try:
        _cleanup(db, barcode, item_id)
        monkeypatch.setattr(barcodes, "get_food", lambda _item_id: {
            "id": item_id,
            "name": "Fresh Mealie Food",
            "unitId": "unit-live",
            "unit": {"name": "Gram", "abbreviation": "g"},
            "aliases": [],
        })
        monkeypatch.setattr(barcodes, "_resolve_notifications_async", lambda *args: None)

        response = barcodes.barcode_map(
            barcode=barcode,
            background_tasks=BackgroundTasks(),
            item_id=item_id,
            quantity="1",
            unit_id="",
            route="inherit",
            shopping_list_ids=[],
            db=db,
        )

        item = db.get(Item, item_id)
        target = db.query(BarcodeTarget).filter(BarcodeTarget.barcode == barcode).one()
        assert response.status_code == 303
        assert item and item.name == "Fresh Mealie Food"
        assert target.target_id == item_id
        assert target.unit_id == "unit-live"
    finally:
        _cleanup(db, barcode, item_id)
        db.close()
