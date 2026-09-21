from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_token
from app.database import SessionLocal, get_db
from app.events import scan_events
from app.models import Activity, BarcodeCache, BarcodeTarget
from app.pause import is_paused
from app.routers import scan as legacy_scan
from app.services.homeassistant import notify_scan as ha_notify_scan
from app.services.targets import ensure_targets
from app.utils import utcnow

logger = logging.getLogger(__name__)
router = APIRouter()

_ROUTE_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="scan-route")
_NOTIFY_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="scan-notify")


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
        if resp.needs_action:
            title = "Routing needs attention"
        elif paused:
            title = "Scanned (scan & link)"
        else:
            title = "Added to destination" if len(targets) == 1 else "Added to destinations"
        _upsert_notification(db, barcode, title, resp.item or barcode, resp.result)
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

    # Resolve only local state here. No Mealie/OpenFoodFacts/UPC request happens
    # before the browser and scanner get acknowledgement for an already-known code.
    item, targets = _local_label(barcode, db)
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
        # Start local/HA feedback immediately and let slow Mealie work continue
        # independently of the scanner HTTP request.
        _NOTIFY_POOL.submit(_notify_received, barcode, item, paused)
        _ROUTE_POOL.submit(_route_known_targets, barcode, [target.id for target in targets], paused)
        return resp

    # Unknown/unmapped codes keep the existing lookup/mapping behaviour. The UI
    # has already received scan-received above, so even a provider timeout does
    # not delay local feedback.
    try:
        resp = legacy_scan._process_scan(barcode, db, background_tasks)
        legacy_scan._queue_ha_notification(resp, barcode, background_tasks)
        return resp
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error processing scan for barcode %s", barcode)
        return legacy_scan._scan_failure(barcode, db, background_tasks)
