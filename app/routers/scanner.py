from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import require_token
from app.config import settings
from app.database import get_db
from app.models import Activity, ApiToken, BarcodeMapping, Item, SystemState
from app.services.shopping import get_shopping_lists
from app.templating import _localtime, _relative_time
from app.utils import utcnow

router = APIRouter()
APP_VERSION = "2026.09.20.1"


@router.post("/scanner/heartbeat")
def scanner_heartbeat(token: ApiToken = Depends(require_token)):
    """Authenticated no-op endpoint; require_token stores scanner telemetry headers."""
    return {
        "ok": True,
        "token": token.name,
        "scanner_version": token.scanner_version,
        "last_seen": token.scanner_last_seen_at.isoformat() if token.scanner_last_seen_at else None,
    }


@router.get("/api/version")
def app_version():
    return {"version": APP_VERSION}


@router.get("/api/scanners")
def scanner_health(db: Session = Depends(get_db)):
    """Session-protected scanner telemetry grouped by the API token that reported it."""
    now = utcnow().replace(tzinfo=None)
    rows = db.query(ApiToken).order_by(ApiToken.name).all()
    scanners = []
    for token in rows:
        if not token.scanner_version:
            continue
        last_seen = token.scanner_last_seen_at
        online = bool(last_seen and last_seen >= now - timedelta(minutes=3))
        scanners.append({
            "token_id": token.id,
            "token_name": token.name,
            "token_prefix": token.token_prefix,
            "version": token.scanner_version,
            "hostname": token.scanner_hostname,
            "device": token.scanner_device,
            "layout": token.scanner_layout,
            "online": online,
            "last_seen": _relative_time(last_seen),
            "last_seen_absolute": _localtime(last_seen),
            "uptime_seconds": token.scanner_uptime_seconds or 0,
            "scans": token.scanner_total_scans or 0,
            "errors": token.scanner_errors or 0,
            "latency_ms": token.scanner_last_latency_ms,
        })
    return {"items": scanners}


@router.get("/api/scanners/recent-scans")
def scanner_recent_scans(limit: int = Query(5, ge=1, le=25), db: Session = Depends(get_db)):
    rows = (
        db.query(Activity)
        .filter(Activity.is_scan_event == True)
        .order_by(Activity.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "barcode": row.barcode,
                "result": row.result,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "target_name": row.target_name,
                "quantity": row.quantity_snapshot,
                "created_at": _relative_time(row.created_at),
                "created_at_absolute": _localtime(row.created_at),
            }
            for row in rows
        ]
    }


@router.get("/api/shopping-lists")
def shopping_lists(force: bool = Query(False)):
    rows = get_shopping_lists(force=force)
    return {
        "default_id": settings.mealie_shopping_list_id,
        "items": [
            {**row, "default": str(row.get("id")) == str(settings.mealie_shopping_list_id)}
            for row in rows
        ],
    }


@router.get("/api/barcode-destination")
def barcode_destination(barcode: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    mapping = db.get(BarcodeMapping, barcode)
    if not mapping:
        return {"mapped": False}
    lists = get_shopping_lists()
    names = {str(row.get("id")): row.get("name") for row in lists}
    if mapping.target_type == "food":
        item = db.get(Item, mapping.target_id)
        route = (item.shopping_route if item else "default") or "default"
        effective_route = "mealie" if route == "default" else route
        list_id = (item.shopping_list_id if item else None) or settings.mealie_shopping_list_id
    else:
        route = "mealie"
        effective_route = "mealie"
        list_id = mapping.shopping_list_id or settings.mealie_shopping_list_id
    return {
        "mapped": True,
        "target_type": mapping.target_type,
        "target_id": mapping.target_id,
        "target_name": mapping.target_name,
        "route": route,
        "effective_route": effective_route,
        "shopping_list_id": list_id,
        "shopping_list_name": names.get(str(list_id), "Configured default" if list_id else None),
        "shopping_list_default": str(list_id) == str(settings.mealie_shopping_list_id),
        "quantity": None if mapping.target_type == "food" and mapping.quantity <= 0.001 else mapping.quantity,
        "unit_id": mapping.unit_id,
    }


_NIIM_FIELDS = {
    "url", "transport", "address", "print_task", "print_direction", "density",
    "label_type", "dpi", "max_label_width_mm", "timeout",
}


@router.get("/api/settings/niim")
def niim_settings(request: Request):
    if not request.session.get("is_admin", False):
        return JSONResponse({"error": "admin required"}, status_code=403)
    from app.services.niimblue import config, printer_status

    cfg = config()
    return {"config": cfg, "status": printer_status()}


@router.post("/api/settings/niim")
async def save_niim_settings(request: Request, db: Session = Depends(get_db)):
    if not request.session.get("is_admin", False):
        return JSONResponse({"error": "admin required"}, status_code=403)
    body = await request.json()
    for field in _NIIM_FIELDS:
        if field not in body:
            continue
        key = f"niimblue.{field}"
        value = str(body.get(field) if body.get(field) is not None else "").strip()
        row = db.get(SystemState, key)
        if row:
            row.value = value
        else:
            db.add(SystemState(key=key, value=value))
    db.commit()
    from app.services.niimblue import config, printer_status

    return {"ok": True, "config": config(), "status": printer_status()}
