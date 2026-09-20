from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import require_token
from app.config import settings
from app.database import get_db
from app.models import Activity, ApiToken, BarcodeMapping, Item, SystemState
from app.services.mealie import check_connectivity
from app.services.shopping import (
    get_default_shopping_list_id,
    get_shopping_list_stats,
    get_shopping_lists,
    set_default_shopping_list_id,
)
from app.services.targets import get_barcode_targets
from app.templating import _localtime, _relative_time
from app.utils import utcnow

router = APIRouter()
APP_VERSION = "2026.09.20.2"


def _admin(request: Request) -> bool:
    return bool(request.session.get("is_admin", False))


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
    default_id = get_default_shopping_list_id(force=force)
    rows = get_shopping_lists(force=force)
    return {
        "default_id": default_id,
        "items": [
            {**row, "default": str(row.get("id")) == str(default_id)}
            for row in rows
        ],
    }


@router.get("/api/shopping-list-stats")
def shopping_list_stats(force: bool = Query(False)):
    return {"items": get_shopping_list_stats(force=force)}


@router.post("/api/settings/default-shopping-list")
async def save_default_shopping_list(request: Request):
    if not _admin(request):
        return JSONResponse({"error": "admin required"}, status_code=403)
    body = await request.json()
    list_id = str((body or {}).get("list_id") or "").strip()
    if not list_id:
        return JSONResponse({"error": "list_id is required"}, status_code=400)
    try:
        selected = set_default_shopping_list_id(list_id)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {"ok": True, "default": selected}


@router.post("/api/settings/test-mealie")
def test_mealie(request: Request):
    if not _admin(request):
        return JSONResponse({"error": "admin required"}, status_code=403)
    connected = check_connectivity()
    lists = get_shopping_lists(force=True) if connected else []
    return JSONResponse({
        "ok": connected,
        "connected": connected,
        "shopping_lists": len(lists),
        "default_id": get_default_shopping_list_id() if connected else None,
    }, status_code=200 if connected else 502)


@router.get("/api/settings/notifications")
def notification_settings(request: Request):
    if not _admin(request):
        return JSONResponse({"error": "admin required"}, status_code=403)
    return {
        "toast_seconds": settings.notification_toast_seconds,
        "group_window_seconds": settings.notification_group_window_seconds,
    }


@router.post("/api/settings/notifications")
async def save_notification_settings(request: Request, db: Session = Depends(get_db)):
    if not _admin(request):
        return JSONResponse({"error": "admin required"}, status_code=403)
    body = await request.json()
    try:
        toast = max(3, min(120, int((body or {}).get("toast_seconds", settings.notification_toast_seconds))))
        grouping = max(1, min(300, int((body or {}).get("group_window_seconds", settings.notification_group_window_seconds))))
        settings.save_override("notification_toast_seconds", str(toast), db)
        settings.save_override("notification_group_window_seconds", str(grouping), db)
    except (TypeError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {"ok": True, "toast_seconds": toast, "group_window_seconds": grouping}


@router.get("/api/barcode-destination")
def barcode_destination(barcode: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    targets = get_barcode_targets(db, barcode)
    if targets:
        lists = get_shopping_lists()
        names = {str(row.get("id")): row.get("name") for row in lists}
        default_id = get_default_shopping_list_id()
        rows = []
        for target in targets:
            list_id = target.shopping_list_id or default_id
            rows.append({
                "id": target.id,
                "primary": target.is_primary,
                "target_type": target.target_type,
                "target_id": target.target_id,
                "target_name": target.target_name,
                "route": target.destination_type,
                "shopping_list_id": list_id,
                "shopping_list_name": names.get(str(list_id)) if list_id else None,
                "shopping_list_default": bool(list_id and str(list_id) == str(default_id)),
                "quantity": target.quantity,
                "unit_id": target.unit_id,
                "recipe_scale": target.recipe_scale,
                "endpoint_url": target.endpoint_url,
            })
        return {"mapped": True, "multi": len(rows) > 1, "targets": rows}

    mapping = db.get(BarcodeMapping, barcode)
    if not mapping:
        return {"mapped": False}
    lists = get_shopping_lists()
    names = {str(row.get("id")): row.get("name") for row in lists}
    default_id = get_default_shopping_list_id()
    if mapping.target_type == "food":
        item = db.get(Item, mapping.target_id)
        route = (item.shopping_route if item else "default") or "default"
        effective_route = "mealie" if route == "default" else route
        list_id = (item.shopping_list_id if item else None) or default_id
    else:
        route = "mealie"
        effective_route = "mealie"
        list_id = mapping.shopping_list_id or default_id
    return {
        "mapped": True,
        "target_type": mapping.target_type,
        "target_id": mapping.target_id,
        "target_name": mapping.target_name,
        "route": route,
        "effective_route": effective_route,
        "shopping_list_id": list_id,
        "shopping_list_name": names.get(str(list_id), "Default list" if list_id else None),
        "shopping_list_default": str(list_id) == str(default_id),
        "quantity": None if mapping.target_type == "food" and mapping.quantity <= 0.001 else mapping.quantity,
        "unit_id": mapping.unit_id,
    }


_NIIM_FIELDS = {
    "url", "transport", "address", "print_task", "print_direction", "density",
    "label_type", "dpi", "max_label_width_mm", "timeout",
}


def _validated_niim_settings(body: dict) -> dict[str, str]:
    values = {
        field: str(body.get(field) if body.get(field) is not None else "").strip()
        for field in _NIIM_FIELDS if field in body
    }
    url = values.get("url")
    if url and not url.startswith(("http://", "https://")):
        raise ValueError("niimblue-node URL must start with http:// or https://")
    transport = values.get("transport")
    if transport and transport not in {"ble", "serial"}:
        raise ValueError("Transport must be ble or serial")
    direction = values.get("print_direction")
    if direction and direction not in {"top", "left", "right", "bottom"}:
        raise ValueError("Print direction must be top, left, right or bottom")

    integer_ranges = {"density": (1, 5), "label_type": (1, 20), "dpi": (100, 1200)}
    float_ranges = {"max_label_width_mm": (1.0, 100.0), "timeout": (1.0, 120.0)}
    for field, (minimum, maximum) in integer_ranges.items():
        if field not in values or values[field] == "":
            continue
        try:
            parsed = int(values[field])
        except ValueError as exc:
            raise ValueError(f"{field} must be an integer") from exc
        if not minimum <= parsed <= maximum:
            raise ValueError(f"{field} must be between {minimum} and {maximum}")
        values[field] = str(parsed)
    for field, (minimum, maximum) in float_ranges.items():
        if field not in values or values[field] == "":
            continue
        try:
            parsed = float(values[field].replace(",", "."))
        except ValueError as exc:
            raise ValueError(f"{field} must be a number") from exc
        if not minimum <= parsed <= maximum:
            raise ValueError(f"{field} must be between {minimum:g} and {maximum:g}")
        values[field] = f"{parsed:g}"
    return values


@router.get("/api/settings/niim")
def niim_settings(request: Request):
    if not _admin(request):
        return JSONResponse({"error": "admin required"}, status_code=403)
    from app.services.niimblue import config, printer_status
    return {"config": config(), "status": printer_status()}


@router.post("/api/settings/niim")
async def save_niim_settings(request: Request, db: Session = Depends(get_db)):
    if not _admin(request):
        return JSONResponse({"error": "admin required"}, status_code=403)
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)
    try:
        values = _validated_niim_settings(body)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    for field, value in values.items():
        key = f"niimblue.{field}"
        row = db.get(SystemState, key)
        if row:
            row.value = value
        else:
            db.add(SystemState(key=key, value=value))
    db.commit()
    from app.services.niimblue import config, printer_status
    return {"ok": True, "config": config(), "status": printer_status()}
