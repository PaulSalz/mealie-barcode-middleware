import json
from pathlib import Path

from app.database import SessionLocal, init_db
from app.models import Activity, BarcodeTarget, Item
from app.routers.dashboard import _recent_scans


ROOT = Path(__file__).resolve().parents[1]


def _cleanup(db, barcode: str, item_id: str) -> None:
    db.query(Activity).filter(Activity.barcode == barcode).delete(synchronize_session=False)
    db.query(BarcodeTarget).filter(BarcodeTarget.barcode == barcode).delete(synchronize_session=False)
    item = db.get(Item, item_id)
    if item:
        db.delete(item)
    db.commit()


def test_recent_scan_uses_current_targets_instead_of_stale_scan_snapshot():
    init_db()
    barcode = "ci-dashboard-current-target"
    item_id = "ci-dashboard-current-food"
    db = SessionLocal()
    try:
        _cleanup(db, barcode, item_id)
        db.add(Item(id=item_id, name="Current food name", source="mealie"))
        db.add(BarcodeTarget(
            barcode=barcode,
            target_type="food",
            target_id=item_id,
            target_name="Stale stored name",
            position=0,
        ))
        db.add(BarcodeTarget(
            barcode=barcode,
            target_type="recipe",
            target_id="current-recipe",
            target_name="Current recipe name",
            position=1,
        ))
        db.add(Activity(
            barcode=barcode,
            title="Scan",
            message="Old food name",
            result="added",
            is_scan_event=True,
            target_type="food",
            target_id="old-food",
            target_name="Old food name",
            targets_json=json.dumps([
                {"type": "food", "id": "old-food", "name": "Old food name"},
            ]),
        ))
        db.commit()

        row = next(row for row in _recent_scans(db, limit=1000) if row["barcode"] == barcode)

        assert row["target_count"] == 2
        assert row["target_name"] == "Current food name"
        assert row["target_id"] == item_id
        assert row["targets"] == [
            {"type": "food", "id": item_id, "name": "Current food name"},
            {"type": "recipe", "id": "current-recipe", "name": "Current recipe name"},
        ]
    finally:
        _cleanup(db, barcode, item_id)
        db.close()


def test_recent_scan_shows_only_a_count_when_multiple_targets_are_linked():
    template = (ROOT / "app/templates/dashboard.html").read_text(encoding="utf-8")
    client = (ROOT / "app/static/js/dashboard-v2.js").read_text(encoding="utf-8")

    assert '{% if item.target_count > 1 %}<span class="badge bg-azure-lt me-1">{{ item.target_count }} targets</span>{% else %}' in template
    assert "if (targetCount > 1) {" in client
    assert "return '<span class=\"badge bg-azure-lt me-1\">' + targetCount + ' targets</span>';" in client


def test_dashboard_recent_rows_prefer_current_target_name_for_linked_food():
    source = (ROOT / "app/routers/dashboard.py").read_text(encoding="utf-8")

    assert "current_targets = targets_by_barcode.get(activity.barcode, [])" in source
    assert 'food_names.get(target.target_id) if target.target_type == "food" else target.target_name' in source
