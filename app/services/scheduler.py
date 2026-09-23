import json
import logging
from datetime import timedelta

import httpx
from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.database import SessionLocal
from app.events import scan_events
from app.models import Activity, Item, RetryQueue
from app.services import mealie_http
from app.services.action_stats import ensure_action_stats_backfilled, purge_action_executions
from app.services.barcode_stats import barcode_stats_ready, ensure_barcode_stats_backfilled
from app.services.mealie_extras import sync_items_enhanced
from app.services.performance_indexes import ensure_performance_indexes
from app.services.scan_stats import ensure_scan_stats_backfilled, purge_raw_scan_history
from app.utils import utcnow

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()
_RAW_SCAN_RETENTION_DAYS = 365
_ACTION_EXECUTION_RETENTION_DAYS = 180
_RETRY_BATCH_SIZE = 50


def _run_item_sync():
    """Background job: sync Mealie items."""
    logger.info("Running scheduled item sync")
    db = SessionLocal()
    try:
        sync_items_enhanced(db)
    except Exception as e:
        logger.error("Scheduled item sync failed: %s", e)
    finally:
        db.close()


def _retry_failed(item: RetryQueue, db, now, message: str) -> None:
    item.attempts += 1
    if item.attempts >= settings.max_retry_attempts:
        _create_retry_failed_activity(item, db)
        db.delete(item)
        logger.warning(
            "Retry permanently failed for %s after %d attempts: %s",
            item.barcode, item.attempts, message,
        )
        return
    backoff = min(2**item.attempts, 480)
    item.next_retry_at = now + timedelta(minutes=backoff)
    logger.warning("Retry failed for %s: %s, next in %dm", item.barcode, message, backoff)


def _process_retry_queue():
    """Retry a bounded batch of failed Mealie shopping-list additions."""
    from app.pause import is_paused

    db = SessionLocal()
    try:
        if is_paused(db):
            logger.debug("Retry queue skipped — shopping list is paused")
            return

        now = utcnow()
        pending = (
            db.query(RetryQueue)
            .filter(RetryQueue.next_retry_at <= now)
            .order_by(RetryQueue.next_retry_at.asc(), RetryQueue.id.asc())
            .limit(_RETRY_BATCH_SIZE)
            .all()
        )
        if not pending:
            return

        logger.info("Processing retry queue batch: %d item(s)", len(pending))
        for item in pending:
            try:
                payload = json.loads(item.payload)
                if not isinstance(payload, dict):
                    raise ValueError("retry payload must be a JSON object")
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                item.attempts = max(item.attempts, settings.max_retry_attempts - 1)
                _retry_failed(item, db, now, f"invalid stored payload ({exc})")
                db.commit()
                continue

            try:
                resp = mealie_http.post(
                    "/api/households/shopping/items",
                    json=payload,
                    timeout=10,
                    log_name="retry shopping item",
                )
            except httpx.HTTPError as exc:
                _retry_failed(item, db, now, str(exc))
                db.commit()
                continue

            if resp.status_code in (200, 201):
                db.delete(item)
                db.commit()
                logger.info("Retry success for barcode=%s", item.barcode)
                continue

            _retry_failed(item, db, now, f"HTTP {resp.status_code}")
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("Retry queue batch failed unexpectedly")
    finally:
        db.close()


def _create_retry_failed_activity(item: RetryQueue, db):
    """Create an activity entry when a retry queue item permanently fails."""
    try:
        payload = json.loads(item.payload)
        item_hint = payload.get("note") or payload.get("foodId") or item.barcode
    except (json.JSONDecodeError, TypeError, AttributeError):
        item_hint = item.barcode

    title = "Failed to add to shopping list"
    message = f"{item_hint} — could not reach Mealie after {item.attempts} retries"

    db.add(Activity(
        barcode=item.barcode,
        title=title,
        message=message,
        result="retry_failed",
    ))

    scan_events.publish_threadsafe("scan", {
        "barcode": item.barcode,
        "result": "retry_failed",
        "item": str(item_hint),
    })


def _purge_old_activities():
    """Bound raw notification, scan and ActionExecution history."""
    db = SessionLocal()
    try:
        cutoff = utcnow() - timedelta(days=7)
        deleted = (
            db.query(Activity)
            .filter(
                Activity.is_read == True,
                Activity.is_scan_event == False,
                Activity.created_at < cutoff,
            )
            .delete()
        )
        db.commit()
        if deleted:
            logger.info("Purged %d old read notification activities", deleted)

        if barcode_stats_ready(db):
            scan_deleted = purge_raw_scan_history(db, _RAW_SCAN_RETENTION_DAYS)
            if scan_deleted:
                logger.info(
                    "Purged %d raw scan activities older than %d days; compact statistics were retained",
                    scan_deleted, _RAW_SCAN_RETENTION_DAYS,
                )
        else:
            logger.warning("Skipping raw scan purge because per-barcode aggregate backfill is incomplete")

        action_deleted = purge_action_executions(db, _ACTION_EXECUTION_RETENTION_DAYS)
        if action_deleted:
            logger.info(
                "Purged %d raw action executions older than %d days; all-time action statistics were retained",
                action_deleted, _ACTION_EXECUTION_RETENTION_DAYS,
            )
    except Exception as e:
        db.rollback()
        logger.error("Activity/history purge failed: %s", e)
    finally:
        db.close()


def start_scheduler():
    """Start background sync, bounded retry processing and history maintenance."""
    ensure_performance_indexes()

    try:
        ensure_scan_stats_backfilled()
    except Exception:
        logger.exception("Could not backfill compact target scan statistics")

    try:
        ensure_barcode_stats_backfilled()
    except Exception:
        logger.exception("Could not backfill compact per-barcode scan statistics")

    try:
        ensure_action_stats_backfilled()
    except Exception:
        logger.exception("Could not backfill durable action statistics")

    db = SessionLocal()
    try:
        if db.query(Item).first() is None:
            logger.info("No items found — running initial Mealie sync")
            try:
                sync_items_enhanced(db)
            except Exception as e:
                logger.warning("Initial sync failed (will retry on schedule): %s", e)
    finally:
        db.close()

    scheduler.add_job(
        _run_item_sync,
        "interval",
        hours=settings.item_sync_interval_hours,
        id="item_sync",
        replace_existing=True,
    )
    scheduler.add_job(
        _process_retry_queue,
        "interval",
        minutes=2,
        id="retry_queue",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _purge_old_activities,
        "interval",
        hours=24,
        id="activity_purge",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("Scheduler started (item sync + bounded retry queue + bounded history purge)")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
