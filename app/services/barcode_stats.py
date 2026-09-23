from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import event, func, text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Activity, SystemState
from app.models_scan_stats import BarcodeDailyStat

logger = logging.getLogger(__name__)
_BACKFILL_KEY = "maintenance.barcode_daily_stats.v1"
_BATCH_SIZE = 1000

_UPSERT = text(
    """
    INSERT INTO barcode_daily_stats (
        barcode, day, count, first_scan, last_scan
    ) VALUES (
        :barcode, :day, :count, :first_scan, :last_scan
    )
    ON CONFLICT(barcode, day) DO UPDATE SET
        count = barcode_daily_stats.count + excluded.count,
        first_scan = CASE
            WHEN excluded.first_scan < barcode_daily_stats.first_scan THEN excluded.first_scan
            ELSE barcode_daily_stats.first_scan
        END,
        last_scan = CASE
            WHEN excluded.last_scan > barcode_daily_stats.last_scan THEN excluded.last_scan
            ELSE barcode_daily_stats.last_scan
        END
    """
)


def _utc_naive(value: datetime | None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _row(activity: Activity) -> dict | None:
    if not activity.is_scan_event or not activity.barcode:
        return None
    created_at = _utc_naive(activity.created_at)
    return {
        "barcode": str(activity.barcode),
        "day": created_at.date(),
        "count": 1,
        "first_scan": created_at,
        "last_scan": created_at,
    }


@event.listens_for(Activity, "after_insert")
def _capture_barcode_scan(_mapper, connection, activity: Activity) -> None:
    row = _row(activity)
    if row:
        connection.execute(_UPSERT, [row])


def ensure_barcode_stats_backfilled() -> int:
    """Build physical-scan barcode counters once from retained raw history."""
    db = SessionLocal()
    processed = 0
    try:
        if db.get(SystemState, _BACKFILL_KEY):
            return 0

        logger.info("Building compact per-barcode statistics from existing Activity history")
        db.query(BarcodeDailyStat).delete(synchronize_session=False)
        db.commit()

        batch: list[dict] = []
        query = (
            db.query(Activity)
            .filter(Activity.is_scan_event == True)
            .order_by(Activity.id.asc())
            .yield_per(500)
        )
        for activity in query:
            row = _row(activity)
            if row:
                batch.append(row)
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
        logger.info("Per-barcode statistics backfill complete (%d scan events)", processed)
        return processed
    except Exception:
        db.rollback()
        logger.exception("Per-barcode statistics backfill failed")
        raise
    finally:
        db.close()


def barcode_stats_ready(db: Session) -> bool:
    return db.get(SystemState, _BACKFILL_KEY) is not None


def barcode_scan_stats(db: Session, barcode: str, *, recent_limit: int = 25) -> dict:
    """Return durable physical-scan counters plus bounded recent raw history."""
    base = db.query(BarcodeDailyStat).filter(BarcodeDailyStat.barcode == barcode)
    total, first_scan, last_scan = base.with_entities(
        func.coalesce(func.sum(BarcodeDailyStat.count), 0),
        func.min(BarcodeDailyStat.first_scan),
        func.max(BarcodeDailyStat.last_scan),
    ).one()

    today = datetime.now(timezone.utc).date()
    days_7 = base.filter(BarcodeDailyStat.day >= today - timedelta(days=6)).with_entities(
        func.coalesce(func.sum(BarcodeDailyStat.count), 0)
    ).scalar()
    days_30 = base.filter(BarcodeDailyStat.day >= today - timedelta(days=29)).with_entities(
        func.coalesce(func.sum(BarcodeDailyStat.count), 0)
    ).scalar()

    recent = (
        db.query(Activity)
        .filter(Activity.is_scan_event == True, Activity.barcode == barcode)
        .order_by(Activity.created_at.desc())
        .limit(max(0, min(int(recent_limit), 100)))
        .all()
    ) if recent_limit else []

    result_rows = (
        db.query(Activity.result, func.count(Activity.id))
        .filter(Activity.is_scan_event == True, Activity.barcode == barcode)
        .group_by(Activity.result)
        .all()
    )

    return {
        "total": int(total or 0),
        "days_7": int(days_7 or 0),
        "days_30": int(days_30 or 0),
        "last_scan": last_scan,
        "first_scan": first_scan,
        "results": {str(result): int(count or 0) for result, count in result_rows},
        "recent": recent,
    }
