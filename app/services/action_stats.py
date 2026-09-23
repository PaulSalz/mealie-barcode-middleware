from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import ActionExecution, SystemState
from app.models_action_stats import ActionAggregate

logger = logging.getLogger(__name__)
_BACKFILL_KEY = "maintenance.action_aggregates.v1"
_BATCH_SIZE = 1000

_UPSERT = text(
    """
    INSERT INTO action_aggregates (
        action_id, total, success, failed, ignored,
        duration_sum_ms, duration_count, last_status, last_execution
    ) VALUES (
        :action_id, :total, :success, :failed, :ignored,
        :duration_sum_ms, :duration_count, :last_status, :last_execution
    )
    ON CONFLICT(action_id) DO UPDATE SET
        total = action_aggregates.total + excluded.total,
        success = action_aggregates.success + excluded.success,
        failed = action_aggregates.failed + excluded.failed,
        ignored = action_aggregates.ignored + excluded.ignored,
        duration_sum_ms = action_aggregates.duration_sum_ms + excluded.duration_sum_ms,
        duration_count = action_aggregates.duration_count + excluded.duration_count,
        last_status = CASE
            WHEN action_aggregates.last_execution IS NULL
              OR excluded.last_execution >= action_aggregates.last_execution
            THEN excluded.last_status ELSE action_aggregates.last_status
        END,
        last_execution = CASE
            WHEN action_aggregates.last_execution IS NULL
              OR excluded.last_execution >= action_aggregates.last_execution
            THEN excluded.last_execution ELSE action_aggregates.last_execution
        END
    """
)


def _utc_naive(value: datetime | None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _row_params(
    action_id: str,
    status: str,
    duration_ms: int | None,
    created_at: datetime | None,
) -> dict:
    duration = int(duration_ms) if duration_ms is not None else 0
    return {
        "action_id": str(action_id),
        "total": 1,
        "success": 1 if status == "success" else 0,
        "failed": 1 if status == "failed" else 0,
        "ignored": 1 if status == "ignored_cooldown" else 0,
        "duration_sum_ms": duration,
        "duration_count": 1 if duration_ms is not None else 0,
        "last_status": str(status),
        "last_execution": _utc_naive(created_at),
    }


def record_action_result(
    db: Session,
    action_id: str,
    status: str,
    *,
    duration_ms: int | None = None,
    created_at: datetime | None = None,
) -> None:
    """Atomically add one terminal action result to all-time statistics."""
    if status == "running":
        return
    db.execute(_UPSERT, _row_params(action_id, status, duration_ms, created_at))


def ensure_action_stats_backfilled() -> int:
    """One-time crash-safe rebuild from existing ActionExecution rows."""
    db = SessionLocal()
    processed = 0
    try:
        if db.get(SystemState, _BACKFILL_KEY):
            return 0

        logger.info("Building durable action statistics from existing execution history")
        db.query(ActionAggregate).delete(synchronize_session=False)
        db.commit()

        batch: list[dict] = []
        query = (
            db.query(ActionExecution)
            .filter(ActionExecution.status != "running")
            .order_by(ActionExecution.id.asc())
            .yield_per(500)
        )
        for execution in query:
            batch.append(_row_params(
                execution.action_id,
                execution.status,
                execution.duration_ms,
                execution.created_at,
            ))
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
        logger.info("Action statistics backfill complete (%d terminal executions)", processed)
        return processed
    except Exception:
        db.rollback()
        logger.exception("Action statistics backfill failed")
        raise
    finally:
        db.close()


def action_stats(db: Session, action_id: str) -> dict:
    row = db.get(ActionAggregate, action_id)
    if not row:
        return {
            "total": 0,
            "success": 0,
            "failed": 0,
            "ignored": 0,
            "avg_ms": None,
            "last_execution": None,
            "last_status": None,
        }
    avg_ms = (
        round(row.duration_sum_ms / row.duration_count, 1)
        if row.duration_count
        else None
    )
    return {
        "total": int(row.total or 0),
        "success": int(row.success or 0),
        "failed": int(row.failed or 0),
        "ignored": int(row.ignored or 0),
        "avg_ms": avg_ms,
        "last_execution": row.last_execution,
        "last_status": row.last_status,
    }


def action_overview(db: Session) -> tuple[dict[str, int], dict[str, dict]]:
    rows = db.query(ActionAggregate).all()
    counts = {row.action_id: int(row.total or 0) for row in rows}
    latest = {
        row.action_id: {"status": row.last_status, "created_at": row.last_execution}
        for row in rows
        if row.last_execution is not None
    }
    return counts, latest


def delete_action_stats(db: Session, action_id: str) -> None:
    row = db.get(ActionAggregate, action_id)
    if row:
        db.delete(row)


def purge_action_executions(db: Session, retention_days: int = 180, *, batch_size: int = 2000) -> int:
    """Bound raw execution detail after durable all-time statistics exist."""
    if not db.get(SystemState, _BACKFILL_KEY):
        logger.warning("Skipping action execution purge because aggregate backfill is incomplete")
        return 0

    cutoff = _utc_naive(datetime.now(timezone.utc) - timedelta(days=max(30, int(retention_days))))
    total = 0
    while True:
        ids = [
            row[0]
            for row in (
                db.query(ActionExecution.id)
                .filter(ActionExecution.created_at < cutoff)
                .order_by(ActionExecution.id.asc())
                .limit(max(100, min(int(batch_size), 10000)))
                .all()
            )
        ]
        if not ids:
            break
        deleted = (
            db.query(ActionExecution)
            .filter(ActionExecution.id.in_(ids))
            .delete(synchronize_session=False)
        )
        db.commit()
        total += int(deleted or 0)
    return total
