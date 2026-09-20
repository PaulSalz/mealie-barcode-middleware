import time

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_token
from app.config import settings
from app.database import get_db
from app.events import scan_events
from app.models import (
    Action,
    ActionExecution,
    Activity,
    BarcodeCache,
    BarcodeMapping,
    BarcodeTarget,
    Item,
    RetryQueue,
)
from app.services.multitarget import route_targets
from app.services.targets import ensure_targets, sync_legacy_primary

router = APIRouter()


@router.post("/api/settings/test-ha-webhook")
def test_ha_webhook():
    url = settings.ha_webhook_url
    if not url:
        return JSONResponse({"ok": False, "error": "HA_WEBHOOK_URL is empty"}, status_code=400)
    payload = {
        "barcode": "TEST",
        "item": "Webhook Test",
        "result_type": "test",
        "action_url": (settings.middleware_base_url.rstrip("/") + "/settings") if settings.middleware_base_url else "/settings",
        "added_to_list": False,
        "paused": False,
    }
    started = time.monotonic()
    try:
        response = httpx.post(url, json=payload, timeout=3)
        elapsed = int((time.monotonic() - started) * 1000)
        ok = response.status_code < 400
        return JSONResponse({
            "ok": ok,
            "status": response.status_code,
            "duration_ms": elapsed,
            "body": response.text[:300],
        }, status_code=200 if ok else 502)
    except httpx.TimeoutException:
        return JSONResponse({"ok": False, "error": "timeout after 3 s"}, status_code=504)
    except httpx.HTTPError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)


class ScannerReceived(BaseModel):
    barcode: str = Field(..., min_length=1, max_length=256)


@router.post("/scanner/received")
def scanner_received(body: ScannerReceived, _token=Depends(require_token)):
    """Acknowledge the physical scan before any potentially slow routing begins."""
    barcode = body.barcode.strip()
    scan_events.publish_threadsafe("received", {"barcode": barcode})
    return {"ok": True}


@router.post("/api/barcodes/{barcode:path}/test-route")
def test_barcode_route(barcode: str, db: Session = Depends(get_db)):
    """Execute configured destinations once without recording a scanner event."""
    targets = ensure_targets(barcode, db)
    if not targets:
        return JSONResponse({"ok": False, "error": "No targets configured for this barcode"}, status_code=404)

    started = time.monotonic()
    routed = route_targets(barcode, targets, db, paused=False)
    elapsed = int((time.monotonic() - started) * 1000)
    results = []
    for row in routed.get("results", []):
        target = row.get("target")
        results.append({
            "target_id": getattr(target, "id", None),
            "target_type": getattr(target, "target_type", None),
            "name": row.get("name"),
            "ok": bool(row.get("ok")),
            "result": row.get("result"),
            "via": row.get("via"),
            "list_ids": row.get("list_ids") or [],
        })
    payload = {
        "ok": bool(routed.get("ok")),
        "result": routed.get("result"),
        "duration_ms": elapsed,
        "targets": results,
        "success_count": sum(1 for row in results if row["ok"]),
        "target_count": len(results),
    }
    return JSONResponse(payload, status_code=200 if payload["ok"] else 502)


class BulkDeleteRequest(BaseModel):
    kind: str
    ids: list[str] = Field(default_factory=list, max_length=500)


@router.post("/api/bulk-delete")
def bulk_delete(body: BulkDeleteRequest, request: Request, db: Session = Depends(get_db)):
    """Delete selected list rows with conservative, type-specific semantics."""
    if not request.session.get("is_admin", False):
        return JSONResponse({"error": "admin required"}, status_code=403)

    ids = list(dict.fromkeys(str(value).strip() for value in body.ids if str(value).strip()))
    if not ids:
        return {"ok": True, "deleted": 0, "skipped": []}

    deleted = 0
    skipped: list[str] = []

    if body.kind == "barcodes":
        db.query(Activity).filter(Activity.barcode.in_(ids)).delete(synchronize_session=False)
        db.query(RetryQueue).filter(RetryQueue.barcode.in_(ids)).delete(synchronize_session=False)
        db.query(BarcodeTarget).filter(BarcodeTarget.barcode.in_(ids)).delete(synchronize_session=False)
        db.query(BarcodeMapping).filter(BarcodeMapping.barcode.in_(ids)).delete(synchronize_session=False)
        deleted = db.query(BarcodeCache).filter(BarcodeCache.barcode.in_(ids)).delete(synchronize_session=False)

    elif body.kind == "activities":
        numeric_ids = []
        for value in ids:
            try:
                numeric_ids.append(int(value))
            except ValueError:
                skipped.append(value)
        if numeric_ids:
            deleted = db.query(Activity).filter(Activity.id.in_(numeric_ids)).delete(synchronize_session=False)

    elif body.kind == "actions":
        actions = db.query(Action).filter(Action.id.in_(ids)).all()
        found = {row.id for row in actions}
        skipped.extend(value for value in ids if value not in found)
        if found:
            db.query(ActionExecution).filter(ActionExecution.action_id.in_(found)).delete(synchronize_session=False)
            action_codes = [f"ACTION:{value}" for value in found]
            db.query(Activity).filter(Activity.barcode.in_(action_codes)).delete(synchronize_session=False)
            db.query(BarcodeCache).filter(BarcodeCache.barcode.in_(action_codes)).delete(synchronize_session=False)
            deleted = db.query(Action).filter(Action.id.in_(found)).delete(synchronize_session=False)

    elif body.kind == "items":
        items = db.query(Item).filter(Item.id.in_(ids)).all()
        by_id = {row.id: row for row in items}
        affected_barcodes: set[str] = set()
        for value in ids:
            item = by_id.get(value)
            if not item or item.source != "manual":
                skipped.append(value)
                continue
            targets = db.query(BarcodeTarget).filter(
                BarcodeTarget.target_type == "food", BarcodeTarget.target_id == value,
            ).all()
            mappings = db.query(BarcodeMapping).filter(
                BarcodeMapping.target_type == "food", BarcodeMapping.target_id == value,
            ).all()
            affected_barcodes.update(row.barcode for row in targets)
            affected_barcodes.update(row.barcode for row in mappings)
            db.query(BarcodeTarget).filter(
                BarcodeTarget.target_type == "food", BarcodeTarget.target_id == value,
            ).delete(synchronize_session=False)
            db.query(BarcodeMapping).filter(
                BarcodeMapping.target_type == "food", BarcodeMapping.target_id == value,
            ).delete(synchronize_session=False)
            db.delete(item)
            deleted += 1
        db.flush()
        for barcode in affected_barcodes:
            sync_legacy_primary(barcode, db)

    else:
        return JSONResponse({"error": "unsupported bulk-delete kind"}, status_code=400)

    db.commit()
    return {"ok": True, "deleted": deleted, "skipped": skipped}
