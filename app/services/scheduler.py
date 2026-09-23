import json
import logging
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.database import SessionLocal
from app.events import scan_events
from app.models import Activity, Item, RetryQueue
from app.services.mealie_extras import sync_items_enhanced
from app.services.scan_stats import ensure_scan_stats_backfilled, purge_raw_scan_history
from app.utils import utcnow

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()
_RAW_SCAN_RETENTION_DAYS = 365


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


def _process_retry_queue():
    """Background job: retry failed Mealie shopping list additions."""
    import httpx
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
            .order_by(RetryQueue.next_retry_at.asc())
            .all()
        )
        if not pending:
            return

        logger.info("Processing %d retry queue items", len(pending))
        headers = {
            "Authorization": f"Bearer {settings.mealie_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        url = f"{settings.mealie_url}/api/households/shopping/items"

        for item in pending:
            try:
                payload = json.loads(item.payload)
                resp = httpx.post(url, headers=headers, json=payload, timeout=10)
                if resp.status_code in (200, 201):
                    db.delete(item)
                    logger.info("Retry success for barcode=%s", item.barcode)
                else:
                    item.attempts += 1
                    if item.attempts >= settings.max_retry_attempts:
                        _create_retry_failed_activity(item, db)
                        db.delete(item)
                        logger.warning(
                            "Retry permanently failed for %s after %d attempts (HTTP %d)",
                            item.barcode, item.attempts, resp.status_code,
                        )
                    else:
                        backoff = min(2**item.attempts, 480)
                        item.next_retry_at = now + timedelta(minutes=backoff)
                        logger.warning(
                            "Retry failed for %s: HTTP %d, next retry in %dm",
                            item.barcode, resp.status_code, backoff,
                        )
            except httpx.HTTPError as e:
                item.attempts += 1
                if item.attempts >= settings.max_retry_attempts:
                    _create_retry_failed_activity(item, db)
                    db.delete(item)
                    logger.warning(
                        "Retry permanently failed for %s after %d attempts: %s",
                        item.barcode, item.attempts, e,
                    )
                else:
                    backoff = min(2**item.attempts, 480)
                    item.next_retry_at = now + timedelta(minutes=backoff)
                    logger.warning("Retry error for %s: %s, next in %dm", item.barcode, e, backoff)

        db.commit()
    finally:
        db.close()


def _create_retry_failed_activity(item: RetryQueue, db):
    """Create an activity entry when a retry queue item permanently fails."""
    try:
        payload = json.loads(item.payload)
        item_hint = payload.get("note") or payload.get("foodId") or item.barcode
    except (json.JSONDecodeError, TypeError):
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
    """Bound notification/raw-scan rows after durable scan aggregates exist."""
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

        scan_deleted = purge_raw_scan_history(db, _RAW_SCAN_RETENTION_DAYS)
        if scan_deleted:
            logger.info(
                "Purged %d raw scan activities older than %d days; compact statistics were retained",
                scan_deleted, _RAW_SCAN_RETENTION_DAYS,
            )
    except Exception as e:
        db.rollback()
        logger.error("Activity/history purge failed: %s", e)
    finally:
        db.close()


def start_scheduler():
    """Start the APScheduler with item sync, history aggregation and retry jobs."""
    # Base.metadata.create_all() has already run before start_scheduler(). The
    # scan-stats service is imported above so its aggregate model is registered
    # before that create_all call, and legacy scan history can now be backfilled.
    try:
        ensure_scan_stats_backfilled()
    except Exception:
        # Raw Activity history remains intact. Do not prevent B2M from starting;
        # a later restart will retry because the completion marker was not set.
        logger.exception("Could not backfill compact scan statistics")

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
    )
    scheduler.add_job(
        _purge_old_activities,
        "interval",
        hours=24,
        id="activity_purge",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started (item sync + retry queue + bounded history purge)")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
