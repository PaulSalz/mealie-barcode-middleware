from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, event, func, or_, text
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


def _recent_target_filter(target_type: str, target_id: str):
    """Match primary and multi-target raw scan snapshots for recent-history UI.

    New statistics never depend on this JSON search; it is used only for the
    bounded list of recent raw Activity rows kept for human-readable history.
    IDs created by B2M/Mealie contain no quotes; LIKE wildcards are escaped.
    """
    escaped = (
        str(target_id)
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
        .replace('"', '\\"')
    )
    escaped_type = str(target_type).replace('"', '\\"')
    spaced = f'%"type": "{escaped_type}", "id": "{escaped}"%'
    compact = f'%"type":"{escaped_type}","id":"{escaped}"%'
    return or_(
        and_(Activity.target_type == target_type, Activity.target_id == target_id),
        Activity.targets_json.like(spaced, escape="\\"),
        Activity.targets_json.like(compact, escape="\\"),
    )


def target_scan_stats(
    db: Session,
    target_type: str,
    target_id: str,
    *,
    recent_limit: int = 25,
) -> dict:
    """Return all-time counters from compact aggregates plus bounded raw history."""
    base = db.query(ScanDailyStat).filter(
        ScanDailyStat.target_type == target_type,
        ScanDailyStat.target_id == target_id,
    )
    total, first_scan, last_scan = base.with_entities(
        func.coalesce(func.sum(ScanDailyStat.count), 0),
        func.min(ScanDailyStat.first_scan),
        func.max(ScanDailyStat.last_scan),
    ).one()

    today = datetime.now(timezone.utc).date()
    days_7 = base.filter(ScanDailyStat.day >= today - timedelta(days=6)).with_entities(
        func.coalesce(func.sum(ScanDailyStat.count), 0)
    ).scalar()
    days_30 = base.filter(ScanDailyStat.day >= today - timedelta(days=29)).with_entities(
        func.coalesce(func.sum(ScanDailyStat.count), 0)
    ).scalar()

    by_barcode_rows = (
        base.with_entities(
            ScanDailyStat.barcode,
            func.sum(ScanDailyStat.count).label("uses"),
            func.max(ScanDailyStat.last_scan).label("last_scan"),
        )
        .group_by(ScanDailyStat.barcode)
        .order_by(func.sum(ScanDailyStat.count).desc(), func.max(ScanDailyStat.last_scan).desc())
        .all()
    )

    recent = (
        db.query(Activity)
        .filter(Activity.is_scan_event == True, _recent_target_filter(target_type, target_id))
        .order_by(Activity.created_at.desc())
        .limit(max(0, min(int(recent_limit), 100)))
        .all()
    ) if recent_limit else []

    return {
        "total": int(total or 0),
        # Daily aggregates intentionally define these as UTC calendar-day windows.
        "days_7": int(days_7 or 0),
        "days_30": int(days_30 or 0),
        "last_scan": last_scan,
        "first_scan": first_scan,
        "recent": recent,
        "by_barcode": [
            {"barcode": barcode, "count": int(uses or 0), "last_scan": last}
            for barcode, uses, last in by_barcode_rows
        ],
    }


def target_usage_summary(db: Session, target_type: str) -> dict[str, dict]:
    """Return all-time count/last-use data for every target of one type."""
    rows = (
        db.query(
            ScanDailyStat.target_id,
            func.sum(ScanDailyStat.count).label("uses"),
            func.max(ScanDailyStat.last_scan).label("last_scan"),
        )
        .filter(ScanDailyStat.target_type == target_type)
        .group_by(ScanDailyStat.target_id)
        .all()
    )
    return {
        str(target_id): {"count": int(uses or 0), "last_scan": last_scan}
        for target_id, uses, last_scan in rows
    }


def frequent_targets(db: Session, target_type: str, limit: int = 6) -> list[dict]:
    """Return the most-used targets without scanning raw Activity history."""
    rows = (
        db.query(
            ScanDailyStat.target_id,
            func.sum(ScanDailyStat.count).label("uses"),
            func.max(ScanDailyStat.last_scan).label("last_scan"),
        )
        .filter(ScanDailyStat.target_type == target_type)
        .group_by(ScanDailyStat.target_id)
        .order_by(func.sum(ScanDailyStat.count).desc(), func.max(ScanDailyStat.last_scan).desc())
        .limit(max(1, min(int(limit), 50)))
        .all()
    )
    result = []
    for target_id, uses, _last_scan in rows:
        latest_name = (
            db.query(ScanDailyStat.target_name)
            .filter(
                ScanDailyStat.target_type == target_type,
                ScanDailyStat.target_id == target_id,
                ScanDailyStat.target_name.isnot(None),
            )
            .order_by(ScanDailyStat.last_scan.desc())
            .first()
        )
        result.append({
            "id": str(target_id),
            "name": latest_name[0] if latest_name and latest_name[0] else str(target_id),
            "uses": int(uses or 0),
        })
    return result


def purge_raw_scan_history(db: Session, retention_days: int, *, batch_size: int = 2000) -> int:
    """Delete old raw scan rows only after the aggregate backfill is complete."""
    if not db.get(SystemState, _BACKFILL_KEY):
        logger.warning("Skipping raw scan purge because aggregate backfill is incomplete")
        return 0

    retention_days = max(30, int(retention_days))
    cutoff = _utc_naive(datetime.now(timezone.utc) - timedelta(days=retention_days))
    total = 0
    while True:
        ids = [
            row[0]
            for row in (
                db.query(Activity.id)
                .filter(Activity.is_scan_event == True, Activity.created_at < cutoff)
                .order_by(Activity.id.asc())
                .limit(max(100, min(int(batch_size), 10000)))
                .all()
            )
        ]
        if not ids:
            break
        deleted = (
            db.query(Activity)
            .filter(Activity.id.in_(ids))
            .delete(synchronize_session=False)
        )
        db.commit()
        total += int(deleted or 0)
    return total


def rebuild_scan_stats(db: Session) -> int:
    """Maintenance helper used by tests/admin repair paths."""
    db.query(ScanDailyStat).delete(synchronize_session=False)
    marker = db.get(SystemState, _BACKFILL_KEY)
    if marker:
        db.delete(marker)
    db.commit()
    return ensure_scan_stats_backfilled()
