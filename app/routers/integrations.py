import time

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.services.multitarget import route_targets
from app.services.targets import ensure_targets

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


@router.post("/api/barcodes/{barcode:path}/test-route")
def test_barcode_route(barcode: str, db: Session = Depends(get_db)):
    """Execute the configured destinations once without recording a scanner event."""
    targets = ensure_targets(barcode, db)
    if not targets:
        return JSONResponse({"ok": False, "error": "No targets configured for this barcode"}, status_code=404)

    routed = route_targets(barcode, targets, db, paused=False)
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
        "targets": results,
    }
    return JSONResponse(payload, status_code=200 if payload["ok"] else 502)
