import json
from datetime import date, datetime

from app.database import SessionLocal, init_db
from app.models import Activity, BarcodeCache, BarcodeMapping, BarcodeTarget, RetryQueue
from app.models_scan_stats import BarcodeDailyStat, ScanDailyStat
from app.routers.barcodes import barcode_delete
from app.routers.dashboard import _recent_scans


def test_delete_food_barcode_removes_mapping_and_recent_scan_history():
    init_db()
    barcode = "FOOD:ci-delete-created-food"
    target_id = "ci-delete-created-food-id"
    now = datetime.utcnow()
    today = now.date()
    db = SessionLocal()
    try:
        db.query(RetryQueue).filter(RetryQueue.barcode == barcode).delete(synchronize_session=False)
        db.query(BarcodeTarget).filter(BarcodeTarget.barcode == barcode).delete(synchronize_session=False)
        db.query(BarcodeMapping).filter(BarcodeMapping.barcode == barcode).delete(synchronize_session=False)
        db.query(Activity).filter(Activity.barcode == barcode).delete(synchronize_session=False)
        db.query(BarcodeDailyStat).filter(BarcodeDailyStat.barcode == barcode).delete(synchronize_session=False)
        db.query(ScanDailyStat).filter(ScanDailyStat.barcode == barcode).delete(synchronize_session=False)

        db.add(BarcodeCache(barcode=barcode, source="generator", title="Created food", found=True))
        db.add(BarcodeMapping(
            barcode=barcode,
            target_type="food",
            target_id=target_id,
            target_name="Created food",
        ))
        db.add(BarcodeTarget(
            barcode=barcode,
            target_type="food",
            target_id=target_id,
            target_name="Created food",
        ))
        db.add(RetryQueue(barcode=barcode, payload="{}"))
        db.add(Activity(
            barcode=barcode,
            title="Food scanned",
            message="Created food",
            result="added",
            is_scan_event=True,
            target_type="food",
            target_id=target_id,
            target_name="Created food",
            targets_json=json.dumps([{"type": "food", "id": target_id, "name": "Created food"}]),
            created_at=now,
        ))
        db.commit()

        assert db.query(BarcodeDailyStat).filter(BarcodeDailyStat.barcode == barcode).count() == 1
        assert db.query(ScanDailyStat).filter(ScanDailyStat.barcode == barcode).count() == 1
        assert any(row["barcode"] == barcode for row in _recent_scans(db, 25))

        response = barcode_delete(barcode, db)

        assert response.status_code == 303
        assert db.get(BarcodeCache, barcode) is None
        assert db.query(BarcodeMapping).filter(BarcodeMapping.barcode == barcode).count() == 0
        assert db.query(BarcodeTarget).filter(BarcodeTarget.barcode == barcode).count() == 0
        assert db.query(RetryQueue).filter(RetryQueue.barcode == barcode).count() == 0
        assert db.query(Activity).filter(Activity.barcode == barcode).count() == 0
        assert db.query(BarcodeDailyStat).filter(BarcodeDailyStat.barcode == barcode).count() == 0
        assert db.query(ScanDailyStat).filter(ScanDailyStat.barcode == barcode).count() == 0
        assert not any(row["barcode"] == barcode for row in _recent_scans(db, 25))
    finally:
        db.query(RetryQueue).filter(RetryQueue.barcode == barcode).delete(synchronize_session=False)
        db.query(BarcodeTarget).filter(BarcodeTarget.barcode == barcode).delete(synchronize_session=False)
        db.query(BarcodeMapping).filter(BarcodeMapping.barcode == barcode).delete(synchronize_session=False)
        db.query(Activity).filter(Activity.barcode == barcode).delete(synchronize_session=False)
        db.query(BarcodeDailyStat).filter(BarcodeDailyStat.barcode == barcode).delete(synchronize_session=False)
        db.query(ScanDailyStat).filter(ScanDailyStat.barcode == barcode).delete(synchronize_session=False)
        cached = db.get(BarcodeCache, barcode)
        if cached:
            db.delete(cached)
        db.commit()
        db.close()
