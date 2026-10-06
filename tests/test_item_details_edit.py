from fastapi import BackgroundTasks
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db
from app.models import BarcodeMapping, BarcodeTarget, Item
from app.routers import barcodes as barcode_router
from app.routers import items as item_router
from app.services.fuzzy import try_auto_map
from app.services.mealie import _food_update_payload
from app.services.schema_migrations import _add_item_default_quantity


def _cleanup(db: Session, item_id: str, barcodes: tuple[str, ...] = ()) -> None:
    db.query(BarcodeTarget).filter(BarcodeTarget.target_id == item_id).delete(synchronize_session=False)
    db.query(BarcodeMapping).filter(BarcodeMapping.target_id == item_id).delete(synchronize_session=False)
    for barcode in barcodes:
        db.query(BarcodeTarget).filter(BarcodeTarget.barcode == barcode).delete(synchronize_session=False)
        mapping = db.get(BarcodeMapping, barcode)
        if mapping:
            db.delete(mapping)
    item = db.get(Item, item_id)
    if item:
        db.delete(item)
    db.commit()


def test_item_default_quantity_migration_adds_safe_default_to_existing_rows():
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE items (id VARCHAR PRIMARY KEY)"))
            conn.execute(text("INSERT INTO items (id) VALUES ('old-food')"))
            _add_item_default_quantity(conn)
            assert conn.execute(text("SELECT default_quantity FROM items WHERE id='old-food'")).scalar() == 1.0
    finally:
        engine.dispose()


def test_food_update_payload_includes_unit_and_preserves_unedited_fields():
    existing = {
        "id": "food-1",
        "unitId": "unit-old",
        "unit": {"id": "unit-old"},
        "aliases": [{"name": "tomato"}],
        "substitutions": [{"substituteFoodId": "food-2", "note": "if unavailable"}],
        "householdsWithIngredientFood": ["household-1"],
        "extras": {"color": "red"},
    }
    payload = _food_update_payload(
        existing,
        name="Tomato",
        plural_name="Tomatoes",
        description="Fresh",
        label_id="label-1",
        unit_id="unit-new",
    )
    assert payload["unitId"] == "unit-new"
    assert payload["aliases"] == existing["aliases"]
    assert payload["substitutions"] == existing["substitutions"]
    assert payload["householdsWithIngredientFood"] == existing["householdsWithIngredientFood"]
    assert payload["extras"] == existing["extras"]

    cleared = _food_update_payload(
        existing, name="Tomato", plural_name=None, description="", label_id=None, unit_id=""
    )
    assert cleared["unitId"] is None

    preserved = _food_update_payload(
        existing, name="Tomato", plural_name=None, description="", label_id=None
    )
    assert preserved["unitId"] == "unit-old"


def test_item_detail_edit_updates_defaults_and_preserves_barcode_overrides(monkeypatch):
    init_db()
    item_id = "ci-item-details-edit"
    default_barcode = "ci-item-edit-default"
    custom_barcode = "ci-item-edit-custom"
    inherited_barcode = "ci-item-edit-inherited"
    db = SessionLocal()
    try:
        _cleanup(db, item_id, (default_barcode, custom_barcode, inherited_barcode))
        db.add(Item(
            id=item_id, name="Before", source="mealie",
            default_quantity=1.0, default_unit_id="unit-old", default_unit_name="each",
            label_id="label-old", label_name="Old category",
        ))
        db.add_all([
            BarcodeTarget(barcode=default_barcode, target_type="food", target_id=item_id,
                          target_name="Before", quantity=1.0, unit_id="unit-old"),
            BarcodeTarget(barcode=custom_barcode, target_type="food", target_id=item_id,
                          target_name="Before", quantity=3.5, unit_id="unit-custom"),
            BarcodeTarget(barcode=inherited_barcode, target_type="food", target_id=item_id,
                          target_name="Before", quantity=None, unit_id=None),
            BarcodeMapping(barcode=default_barcode, target_type="food", target_id=item_id,
                           target_name="Before", quantity=1.0, unit_id="unit-old"),
        ])
        db.commit()

        calls = {}
        def fake_update_food(_item_id, **kwargs):
            calls.update(item_id=_item_id, **kwargs)
            return {
                "id": item_id,
                "name": kwargs["name"],
                "pluralName": kwargs["plural_name"],
                "description": kwargs["description"],
                "labelId": kwargs["label_id"],
                "label": {"id": kwargs["label_id"], "name": "Pantry"},
                "unitId": kwargs["unit_id"],
                "unit": {"id": kwargs["unit_id"], "name": "Pack", "abbreviation": "pk"},
                "aliases": [{"name": "tomato"}],
            }

        monkeypatch.setattr(item_router, "update_food", fake_update_food)
        monkeypatch.setattr(item_router, "cached_labels", lambda: [{"id": "label-new", "name": "Pantry"}])
        monkeypatch.setattr(item_router, "cached_units", lambda: [{"id": "unit-new", "name": "Pack", "abbreviation": "pk"}])
        monkeypatch.setattr(item_router, "clear_catalog_cache", lambda: None)

        response = item_router.edit_mealie_item(
            item_id=item_id,
            background_tasks=BackgroundTasks(),
            name="After",
            plural_name="Afters",
            description="Updated description",
            label_id="label-new",
            unit_id="unit-new",
            default_quantity=2.75,
            db=db,
        )

        assert response.status_code == 303
        assert response.headers["location"] == f"/items/{item_id}?saved=1"
        assert calls["unit_id"] == "unit-new"
        assert calls["label_id"] == "label-new"
        assert calls["description"] == "Updated description"

        item = db.get(Item, item_id)
        assert item.name == "After"
        assert item.default_quantity == 2.75
        assert item.default_unit_id == "unit-new"
        assert item.default_unit_name == "Pack"
        assert item.label_id == "label-new"
        assert item.label_name == "Pantry"

        targets = {row.barcode: row for row in db.query(BarcodeTarget).filter(BarcodeTarget.target_id == item_id).all()}
        assert targets[default_barcode].quantity == 2.75
        assert targets[default_barcode].unit_id == "unit-new"
        assert targets[custom_barcode].quantity == 3.5
        assert targets[custom_barcode].unit_id == "unit-custom"
        assert targets[inherited_barcode].quantity == 2.75
        assert targets[inherited_barcode].unit_id == "unit-new"
        mapping = db.get(BarcodeMapping, default_barcode)
        assert mapping.quantity == 2.75
        assert mapping.unit_id == "unit-new"
    finally:
        _cleanup(db, item_id, (default_barcode, custom_barcode, inherited_barcode))
        db.close()


def test_new_item_barcode_targets_use_the_item_default_quantity(monkeypatch):
    init_db()
    item_id = "ci-food-item-default-quantity"
    auto_barcode = "ci-auto-default-quantity"
    manual_barcode = "ci-manual-default-quantity"
    db = SessionLocal()
    try:
        _cleanup(db, item_id, (auto_barcode, manual_barcode))
        db.add(Item(
            id=item_id, name="Default quantity food", source="mealie",
            default_quantity=2.5, default_unit_id="unit-pack",
        ))
        db.commit()

        assert try_auto_map(auto_barcode, "Default quantity food", None, db) == item_id
        auto_target = db.query(BarcodeTarget).filter(BarcodeTarget.barcode == auto_barcode).one()
        assert auto_target.quantity == 2.5
        assert auto_target.unit_id == "unit-pack"

        monkeypatch.setattr(barcode_router, "get_food", lambda _item_id: None)
        monkeypatch.setattr(barcode_router, "_resolve_notifications_async", lambda *args: None)
        response = barcode_router.barcode_map(
            barcode=manual_barcode,
            background_tasks=BackgroundTasks(),
            item_id=item_id,
            quantity="",
            unit_id="",
            route="inherit",
            shopping_list_ids=[],
            db=db,
        )
        manual_target = db.query(BarcodeTarget).filter(BarcodeTarget.barcode == manual_barcode).one()
        assert response.status_code == 303
        assert manual_target.quantity == 2.5
        assert manual_target.unit_id == "unit-pack"
    finally:
        _cleanup(db, item_id, (auto_barcode, manual_barcode))
        db.close()


def test_item_details_form_exposes_quantity_unit_category_and_description():
    from pathlib import Path

    template = Path("app/templates/item_detail.html").read_text(encoding="utf-8")
    assert 'name="default_quantity"' in template
    assert 'name="unit_id"' in template
    assert 'name="label_id"' in template
    assert 'name="description"' in template
    assert "Default scan quantity" in template
    assert "Default unit" in template
