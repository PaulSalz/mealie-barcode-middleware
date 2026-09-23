from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_token, require_token_no_telemetry
from app.database import SessionLocal, get_db
from app.events import scan_events
from app.models import Activity, BarcodeCache, BarcodeTarget
from app.pause import is_paused
from app.routers import scan as legacy_scan
from app.services.bounded_executor import BoundedExecutor, ExecutorSaturated
from app.services.homeassistant import notify_scan as ha_notify_scan
from app.services.targets import ensure_targets
from app.utils import utcnow

logger = logging.getLogger(__name__)
router = APIRouter()

# Keep slow network side effects completely outside the scanner HTTP request, but
# cap both running and queued work. ThreadPoolExecutor's native queue is unbounded.
_ROUTE_POOL = BoundedExecutor(max_workers=4, max_pending=32, thread_name_prefix="scan-route")
_NOTIFY_POOL = BoundedExecutor(max_workers=4, max_pending=32, thread_name_prefix="scan-notify")


def _local_label(barcode: str, db: Session) -> tuple[str, list[BarcodeTarget]]:
    targets = ensure_targets(barcode, db)
    enabled = [target for target in targets if target.enabled]
    if enabled:
        names = [target.target_name or target.target_id for target in enabled]
        text = " + ".join(names[:3])
        if len(names) > 3:
            text += f" +{len(names) - 3}"
        return text or barcode, enabled
    cached = db.get(BarcodeCache, barcode)
    return ((cached.display_title if cached else None) or barcode), []


def _upsert_notification(db: Session, barcode: str, title: str, message: str, result: str) -> None:
    row = (
        db.query(Activity)
        .filter(
            Activity.barcode == barcode,
            Activity.is_scan_event == False,
            Activity.is_read == False,
            Activity.is_dismissed == False,
        )
        .order_by(Activity.created_at.desc())
        .first()
    )
    if row:
        row.title = title
        row.message = message
        row.result = result
        row.created_at = utcnow()
    else:
        db.add(Activity(
            barcode=barcode,
            title=title,
            message=message,
            result=result,
            is_read=False,
            is_dismissed=False,
            is_scan_event=False,
            created_at=utcnow(),
        ))
    db.commit()


def _emit_received(barcode: str, item: str, target_count: int) -> None:
    scan_events.publish_threadsafe("scan-received", {
        "barcode": barcode,
        "item": item,
        "result": "processing",
        "target_count": target_count,
    })


def _notify_received(barcode: str, item: str, paused: bool) -> None:
    try:
        ha_notify_scan(
            barcode,
            item,
            "processing",
            legacy_scan._build_action_url(barcode),
            False,
            paused,
        )
    except Exception:
        logger.exception("Immediate HA scan notification failed for %s", barcode)


def _notification_title(resp: legacy_scan.ScanResponse, target_count: int = 0) -> str:
    if resp.result == "error":
        return "Routing failed"
    if resp.result == "partial":
        return "Routing needs attention"
    if resp.result in {"unknown", "unknown_action"}:
        return "Unknown barcode" if resp.result == "unknown" else "Unknown action"
    if resp.result in {"needs_mapping", "auto_mapped"}:
        return "Not linked" if resp.result == "needs_mapping" else "Auto-linked — review"
    if resp.result == "queued":
        return "Queued for retry"
    if resp.result == "added_as_note":
        return "Added as note"
    if resp.paused:
        return "Scanned (scan & link)"
    if resp.result == "added":
        return "Added to destination" if target_count <= 1 else "Added to destinations"
    return "Scan processed"


def _route_known_targets(barcode: str, target_ids: list[int], paused: bool) -> None:
    db = SessionLocal()
    try:
        rows = (
            db.query(BarcodeTarget)
            .filter(BarcodeTarget.id.in_(target_ids), BarcodeTarget.enabled == True)
            .all()
        )
        by_id = {row.id: row for row in rows}
        targets = [by_id[target_id] for target_id in target_ids if target_id in by_id]
        if not targets:
            raise RuntimeError("No enabled targets remain for this barcode")

        resp = legacy_scan._process_targets(barcode, targets, db, paused)
        _upsert_notification(
            db,
            barcode,
            _notification_title(resp, len(targets)),
            resp.item or barcode,
            resp.result,
        )
    except Exception as exc:
        db.rollback()
        logger.exception("Deferred routing failed for barcode %s", barcode)
        message = str(exc) or "Deferred routing failed"
        try:
            _upsert_notification(db, barcode, "Routing failed", message, "error")
            legacy_scan._save_activity(barcode, "Routing failed", message, "error", db)
        except Exception:
            db.rollback()
        legacy_scan._emit_scan_event(
            barcode,
            legacy_scan.ScanResponse(
                result="error",
                item=barcode,
                needs_action=True,
                action_url=legacy_scan._build_action_url(barcode),
                paused=paused,
            ),
        )
    finally:
        db.close()


@router.post("/scanner/received")
def fast_scanner_received(
    body: legacy_scan.ScanRequest,
    _token=Depends(require_token_no_telemetry),
    db: Session = Depends(get_db),
):
    """Record the physical scanner receipt before /scan routing starts.

    The USB bridge sends this request independently from /scan. Keeping the
    receipt entirely local makes UI feedback deterministic even if lookup or
    Mealie routing takes seconds. The later /scan request updates the same
    unread notification with the final result.
    """
    barcode = body.barcode.strip()
    if not barcode:
        raise HTTPException(status_code=422, detail="Barcode cannot be empty")
    item, targets = _local_label(barcode, db)
    _upsert_notification(db, barcode, "Scan received", item, "processing")
    logger.info("Scanner received barcode=%r targets=%d", barcode, len(targets))
    scan_events.publish_threadsafe("received", {
        "barcode": barcode,
        "item": item,
        "result": "processing",
        "target_count": len(targets),
    })
    return {"ok": True, "barcode": barcode, "target_count": len(targets)}


@router.post("/scan", response_model=legacy_scan.ScanResponse)
def fast_scan_barcode(
    body: legacy_scan.ScanRequest,
    background_tasks: BackgroundTasks,
    _token=Depends(require_token),
    db: Session = Depends(get_db),
):
    barcode = body.barcode.strip()
    if not barcode:
        raise HTTPException(status_code=422, detail="Barcode cannot be empty")

    # Resolve local SQLite state first. For an already-linked barcode this path
    # performs no OpenFoodFacts/UPC/Mealie request before acknowledgement.
    item, targets = _local_label(barcode, db)

    # The red notification dot and scan-received SSE are committed/emitted before
    # any external routing begins, so the UI reacts immediately. If the scanner's
    # /scanner/received request already created this row, this only updates it.
    _upsert_notification(db, barcode, "Scan received", item, "processing")
    _emit_received(barcode, item, len(targets))

    if targets:
        paused = is_paused(db)
        resp = legacy_scan.ScanResponse(
            result="processing",
            item=item,
            via="multi" if len(targets) > 1 else "deferred",
            needs_action=False,
            action_url=legacy_scan._build_action_url(barcode),
            paused=paused,
        )

        # Admission to the routing pool happens before the HTTP acknowledgement.
        # If capacity is exhausted, return 503 so the persistent scanner outbox
        # retains this delivery and retries later rather than losing the route.
        try:
            _ROUTE_POOL.submit(_route_known_targets, barcode, [target.id for target in targets], paused)
        except ExecutorSaturated as exc:
            logger.warning("Scan routing queue saturated for barcode %s", barcode)
            raise HTTPException(status_code=503, detail="Scan routing queue is busy; retry shortly") from exc

        # HA's immediate "processing" notification is best-effort and must never
        # consume the reliability budget reserved for actual shopping routing.
        try:
            _NOTIFY_POOL.submit(_notify_received, barcode, item, paused)
        except ExecutorSaturated:
            logger.warning("Scan notification queue saturated for barcode %s", barcode)
        return resp

    # Unknown/unmapped codes retain the current lookup/mapping behaviour. The web
    # UI has nevertheless already received the local event above, so provider
    # latency no longer delays visual acknowledgement.
    try:
        resp = legacy_scan._process_scan(barcode, db, background_tasks)
        _upsert_notification(db, barcode, _notification_title(resp), resp.item or item, resp.result)
        legacy_scan._queue_ha_notification(resp, barcode, background_tasks)
        return resp
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error processing scan for barcode %s", barcode)
        resp = legacy_scan._scan_failure(barcode, db, background_tasks)
        try:
            _upsert_notification(db, barcode, "Scan failed", resp.item or barcode, "error")
        except Exception:
            db.rollback()
        return resp
