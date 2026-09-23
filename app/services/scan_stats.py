from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Activity, SystemState
from app.models_scan_stats import ScanDailyStat

logger = logging.getLogger(__name__)
_BACKFILL_KEY = "maintenance.scan_daily_stats.v1"
_BATCH_SIZE = 1000

_UPSERT = text(
    """
    INSERT INTO scan_daily_stats (
        target_type, target_id, barcode, day, target_name,
        count, first_scan, last_scan
    ) VALUES (
        :target_type, :target_id, :barcode, :day, :target_name,
        :count, :first_scan, :last_scan
    )
    ON CONFLICT(target_type, target_id, barcode, day) DO UPDATE SET
        count = scan_daily_stats.count + excluded.count,
        target_name = COALESCE(excluded.target_name, scan_daily_stats.target_name),
        first_scan = CASE
            WHEN excluded.first_scan < scan_daily_stats.first_scan THEN excluded.first_scan
            ELSE scan_daily_stats.first_scan
        END,
        last_scan = CASE
            WHEN excluded.last_scan > scan_daily_stats.last_scan THEN excluded.last_scan
            ELSE scan_daily_stats.last_scan
        END
    """
)


def _utc_naive(value: datetime | None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def activity_targets(activity: Activity) -> list[dict]:
    """Return unique target snapshots represented by one physical scan."""
    rows: list[dict] = []
    if activity.targets_json:
        try:
            decoded = json.loads(activity.targets_json)
            if isinstance(decoded, list):
                rows.extend(row for row in decoded if isinstance(row, dict))
        except (TypeError, ValueError):
            pass
    if not rows and activity.target_type and activity.target_id:
        rows.append({
            "type": activity.target_type,
            "id": activity.target_id,
            "name": activity.target_name,
        })

    unique: dict[tuple[str, str], dict] = {}
    for row in rows:
        target_type = str(row.get("type") or "").strip()
        target_id = str(row.get("id") or "").strip()
        if not target_type or not target_id:
            continue
        unique[(target_type, target_id)] = {
            "type": target_type,
            "id": target_id,
            "name": str(row.get("name") or "").strip() or None,
        }
    return list(unique.values())


def _aggregate_rows(activity: Activity) -> list[dict]:
    if not activity.is_scan_event:
        return []
    created_at = _utc_naive(activity.created_at)
    return [
        {
            "target_type": row["type"],
            "target_id": row["id"],
            "barcode": str(activity.barcode),
            "day": created_at.date(),
            "target_name": row.get("name"),
            "count": 1,
            "first_scan": created_at,
            "last_scan": created_at,
        }
        for row in activity_targets(activity)
    ]


@event.listens_for(Activity, "after_insert")
def _capture_scan_activity(_mapper, connection, activity: Activity) -> None:
    """Update compact stats in the same transaction as the raw Activity row."""
    rows = _aggregate_rows(activity)
    if rows:
        connection.execute(_UPSERT, rows)


def ensure_scan_stats_backfilled() -> int:
    """Build aggregates once for scan rows created before this feature existed.

    A partial/crashed backfill is harmless: without the completion marker the
    next startup clears the partial aggregate table and rebuilds it from raw scan
    history before the application starts serving requests.
    """
    db = SessionLocal()
    processed = 0
    try:
        if db.get(SystemState, _BACKFILL_KEY):
            return 0

        logger.info("Building compact scan statistics from existing Activity history")
        db.query(ScanDailyStat).delete(synchronize_session=False)
        db.commit()

        batch: list[dict] = []
        query = (
            db.query(Activity)
            .filter(Activity.is_scan_event == True)
            .order_by(Activity.id.asc())
            .yield_per(500)
        )
        for activity in query:
            batch.extend(_aggregate_rows(activity))
            processed += 1
            if len(batch) >= _BATCH_SIZE:
                db.execute(_UPSERT, batch)
                db.commit()
                batch.clear()
        if batch:
            db.execute(_UPSERT, batch)
            db.commit()

        db.add(SystemState(key=_BACKFILL_KEY, value="complete"))
        db.commit()
        logger.info("Scan statistics backfill complete (%d scan events)", processed)
        return processed
    except Exception:
        db.rollback()
        logger.exception("Scan statistics backfill failed")
        raise
    finally:
        db.close()


def rebuild_scan_stats(db: Session) -> int:
    """Maintenance helper used by tests/admin repair paths."""
    db.query(ScanDailyStat).delete(synchronize_session=False)
    marker = db.get(SystemState, _BACKFILL_KEY)
    if marker:
        db.delete(marker)
    db.commit()
    return ensure_scan_stats_backfilled()
