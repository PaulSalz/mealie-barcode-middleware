import json

from app.database import SessionLocal, init_db
from app.models import Activity
from app.models_scan_stats import BarcodeDailyStat
from app.services.barcode_stats import barcode_scan_stats


def test_multi_target_activity_counts_as_one_physical_barcode_scan():
    init_db()
    barcode = "ci-multi-target-physical-scan"
    db = SessionLocal()
    try:
        db.query(Activity).filter(Activity.barcode == barcode).delete(synchronize_session=False)
        db.query(BarcodeDailyStat).filter(BarcodeDailyStat.barcode == barcode).delete(synchronize_session=False)
        db.commit()

        db.add(Activity(
            barcode=barcode,
            title="Multi target scan",
            message="Food + Recipe",
            result="added",
            is_read=True,
            is_dismissed=True,
            is_scan_event=True,
            target_type="food",
            target_id="food-a",
            target_name="Food A",
            targets_json=json.dumps([
                {"type": "food", "id": "food-a", "name": "Food A"},
                {"type": "recipe", "id": "recipe-b", "name": "Recipe B"},
            ]),
        ))
        db.commit()

        stats = barcode_scan_stats(db, barcode)
        assert stats["total"] == 1
        assert stats["days_7"] == 1
        assert stats["days_30"] == 1
        assert len(stats["recent"]) == 1
    finally:
        db.query(Activity).filter(Activity.barcode == barcode).delete(synchronize_session=False)
        db.query(BarcodeDailyStat).filter(BarcodeDailyStat.barcode == barcode).delete(synchronize_session=False)
        db.commit()
        db.close()
