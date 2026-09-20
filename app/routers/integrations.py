import time

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings

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
