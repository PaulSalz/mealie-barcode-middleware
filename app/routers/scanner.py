import json
from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import require_token
from app.config import settings
from app.database import get_db
from app.models import Activity, ApiToken, BarcodeMapping, BarcodeTarget, Item, SystemState
from app.services.shopping import (
    get_default_shopping_list_id,
    get_shopping_list_counts,
    get_shopping_lists,
    set_default_shopping_list_id,
    test_mealie_connection,
)
from app.templating import _localtime, _relative_time
from app.utils import utcnow

router = APIRouter()
APP_VERSION = "2026.09.20.3"


def _scanner_state(token: ApiToken, now=None) -> tuple[bool, bool, str]:
    """Return bridge-online, hardware-connected and a stable device status."""
    if now is None:
        now = utcnow().replace(tzinfo=None)
    last_seen = token.scanner_last_seen_at
    bridge_online = bool(last_seen and last_seen >= now - timedelta(minutes=3))
    device = (token.scanner_device or "").strip()
    disconnected_values = {"", "disconnected", "none", "offline", "unknown"}
    device_connected = bool(bridge_online and device.casefold() not in disconnected_values)
    if not bridge_online:
        status = "bridge_offline"
    elif device_connected:
        status = "connected"
    else:
        status = "disconnected"
    return bridge_online, device_connected, status


@router.post("/scanner/heartbeat")
def scanner_heartbeat(token: ApiToken = Depends(require_token)):
    bridge_online, device_connected, status = _scanner_state(token)
    return {
        "ok": True,
        "token": token.name,
        "scanner_version": token.scanner_version,
        "bridge_online": bridge_online,
        "device_connected": device_connected,
        "status": status,
        "device": token.scanner_device,
        "last_seen": token.scanner_last_seen_at.isoformat() if token.scanner_last_seen_at else None,
    }


@router.get("/api/version")
def app_version():
    return {"version": APP_VERSION}


@router.get("/api/scanners")
def scanner_health(db: Session = Depends(get_db)):
    now = utcnow().replace(tzinfo=None)
    scanners = []
    for token in db.query(ApiToken).order_by(ApiToken.name).all():
        if not token.scanner_version:
            continue
        last_seen = token.scanner_last_seen_at
        bridge_online, device_connected, status = _scanner_state(token, now)
        device = (token.scanner_device or "").strip()
        host = token.scanner_hostname or "Unknown host"
        if status == "disconnected":
            host_display = f"{host} · USB scanner disconnected"
        elif status == "bridge_offline":
            host_display = f"{host} · bridge offline"
        else:
            host_display = host
        scanners.append({
            "token_id": token.id,
            "token_name": token.name,
            "token_prefix": token.token_prefix,
            "version": token.scanner_version,
            "hostname": token.scanner_hostname,
            "hostname_display": host_display,
            "device": device or "disconnected",
            "layout": token.scanner_layout,
            # Backward-compatible: `online` continues to mean the bridge is reporting.
            "online": bridge_online,
            "bridge_online": bridge_online,
            "device_connected": device_connected,
            "status": status,
            "status_label": "Scanner connected" if device_connected else ("USB scanner disconnected" if bridge_online else "Bridge offline"),
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
    rows = db.query(Activity).filter(Activity.is_scan_event == True).order_by(Activity.created_at.desc()).limit(limit).all()
    return {"items": [{
        "id": row.id, "barcode": row.barcode, "result": row.result,
        "target_type": row.target_type, "target_id": row.target_id, "target_name": row.target_name,
        "quantity": row.quantity_snapshot, "created_at": _relative_time(row.created_at),
        "created_at_absolute": _localtime(row.created_at),
    } for row in rows]}


def _require_admin_json(request: Request):
    if not request.session.get("is_admin", False):
        return JSONResponse({"error": "admin required"}, status_code=403)
    return None


@router.get("/api/shopping-lists")
def shopping_lists(force: bool = Query(False), db: Session = Depends(get_db)):
    rows = get_shopping_lists(force=force)
    default_id = get_default_shopping_list_id(db, force_lists=force)
    return {"default_id": default_id, "items": [{**row, "default": str(row.get("id")) == str(default_id)} for row in rows]}


@router.get("/api/shopping-lists/counts")
def shopping_list_counts(force: bool = Query(False)):
    return {"items": get_shopping_list_counts(force=force)}


@router.post("/api/settings/mealie/default-list")
async def save_default_list(request: Request, db: Session = Depends(get_db)):
    if denied := _require_admin_json(request): return denied
    body = await request.json()
    try: list_id = set_default_shopping_list_id(str(body.get("list_id") or ""), db)
    except ValueError as exc: return JSONResponse({"error": str(exc)}, status_code=400)
    return {"ok": True, "default_id": list_id}


@router.post("/api/settings/mealie/test")
def test_mealie(request: Request):
    if denied := _require_admin_json(request): return denied
    result = test_mealie_connection()
    return JSONResponse(result, status_code=200 if result.get("ok") else 502)


@router.get("/api/settings/notifications")
def notification_settings():
    # Non-sensitive UI timing is readable by any authenticated web session; the
    # auth middleware still protects /api/* pages. Mutations stay admin-only.
    return {"toast_seconds": settings.notification_toast_seconds, "group_window_seconds": settings.notification_group_window_seconds}


@router.post("/api/settings/notifications")
async def save_notification_settings(request: Request, db: Session = Depends(get_db)):
    if denied := _require_admin_json(request): return denied
    body = await request.json()
    try:
        toast = max(3, min(120, int(body.get("toast_seconds", settings.notification_toast_seconds))))
        group = max(1, min(300, int(body.get("group_window_seconds", settings.notification_group_window_seconds))))
        settings.save_override("notification_toast_seconds", str(toast), db)
        settings.save_override("notification_group_window_seconds", str(group), db)
    except (TypeError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {"ok": True, "toast_seconds": toast, "group_window_seconds": group}


def _target_lists(target: BarcodeTarget) -> list[str]:
    try:
        values = json.loads(target.shopping_list_ids_json or "[]")
        return [str(value) for value in values if value]
    except (TypeError, ValueError): return []


@router.get("/api/barcode-destination")
def barcode_destination(barcode: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    targets = db.query(BarcodeTarget).filter(BarcodeTarget.barcode == barcode, BarcodeTarget.enabled == True).order_by(BarcodeTarget.position, BarcodeTarget.id).all()
    mapping = db.get(BarcodeMapping, barcode)
    if not targets and not mapping: return {"mapped": False, "targets": []}
    lists = get_shopping_lists(); names = {str(row.get("id")): row.get("name") for row in lists}; default_id = get_default_shopping_list_id(db)
    result = []
    if targets:
        for target in targets:
            item = db.get(Item, target.target_id) if target.target_type == "food" else None
            route = target.route or "inherit"
            effective_route = ((item.shopping_route or "default") if item else "mealie") if route == "inherit" else route
            if effective_route == "default": effective_route = "mealie"
            ids = _target_lists(target)
            if not ids and item and item.shopping_list_id: ids = [item.shopping_list_id]
            if not ids and default_id: ids = [default_id]
            result.append({
                "id": target.id, "target_type": target.target_type, "target_id": target.target_id, "target_name": target.target_name,
                "route": route, "effective_route": effective_route, "shopping_list_ids": ids,
                "shopping_lists": [{"id": value, "name": names.get(str(value), str(value)), "default": str(value) == str(default_id)} for value in ids],
                "quantity": target.quantity, "unit_id": target.unit_id, "recipe_scale": target.recipe_scale,
            })
    elif mapping:
        item = db.get(Item, mapping.target_id) if mapping.target_type == "food" else None
        list_id = (item.shopping_list_id if item else mapping.shopping_list_id) or default_id
        result.append({
            "id": None, "target_type": mapping.target_type, "target_id": mapping.target_id, "target_name": mapping.target_name,
            "route": "inherit", "effective_route": (item.shopping_route if item and item.shopping_route not in {None, "default"} else "mealie"),
            "shopping_list_ids": [list_id] if list_id else [],
            "shopping_lists": [{"id": list_id, "name": names.get(str(list_id), str(list_id)), "default": str(list_id) == str(default_id)}] if list_id else [],
            "quantity": None if mapping.target_type == "food" and mapping.quantity <= 0.001 else mapping.quantity,
            "unit_id": mapping.unit_id, "recipe_scale": mapping.recipe_scale,
        })
    return {"mapped": True, "targets": result, "default_id": default_id}


_NIIM_FIELDS = {"url", "transport", "address", "print_task", "print_direction", "density", "label_type", "dpi", "max_label_width_mm", "timeout"}


def _validated_niim_settings(body: dict) -> dict[str, str]:
    values = {field: str(body.get(field) if body.get(field) is not None else "").strip() for field in _NIIM_FIELDS if field in body}
    url = values.get("url")
    if url and not url.startswith(("http://", "https://")): raise ValueError("niimblue-node URL must start with http:// or https://")
    transport = values.get("transport")
    if transport and transport not in {"ble", "serial"}: raise ValueError("Transport must be ble or serial")
    direction = values.get("print_direction")
    if direction and direction not in {"top", "left", "right", "bottom"}: raise ValueError("Print direction must be top, left, right or bottom")
    for field, (minimum, maximum) in {"density": (1, 5), "label_type": (1, 20), "dpi": (100, 1200)}.items():
        if field not in values or values[field] == "": continue
        try: parsed = int(values[field])
        except ValueError as exc: raise ValueError(f"{field} must be an integer") from exc
        if not minimum <= parsed <= maximum: raise ValueError(f"{field} must be between {minimum} and {maximum}")
        values[field] = str(parsed)
    for field, (minimum, maximum) in {"max_label_width_mm": (1.0, 100.0), "timeout": (1.0, 120.0)}.items():
        if field not in values or values[field] == "": continue
        try: parsed = float(values[field].replace(",", "."))
        except ValueError as exc: raise ValueError(f"{field} must be a number") from exc
        if not minimum <= parsed <= maximum: raise ValueError(f"{field} must be between {minimum:g} and {maximum:g}")
        values[field] = f"{parsed:g}"
    return values


@router.get("/api/settings/niim")
def niim_settings(request: Request):
    if denied := _require_admin_json(request): return denied
    from app.services.niimblue import config, printer_status
    return {"config": config(), "status": printer_status()}


@router.post("/api/settings/niim")
async def save_niim_settings(request: Request, db: Session = Depends(get_db)):
    if denied := _require_admin_json(request): return denied
    body = await request.json()
    if not isinstance(body, dict): return JSONResponse({"error": "JSON object required"}, status_code=400)
    try: values = _validated_niim_settings(body)
    except ValueError as exc: return JSONResponse({"error": str(exc)}, status_code=400)
    for field, value in values.items():
        key = f"niimblue.{field}"; row = db.get(SystemState, key)
        if row: row.value = value
        else: db.add(SystemState(key=key, value=value))
    db.commit()
    from app.services.niimblue import config, printer_status
    return {"ok": True, "config": config(), "status": printer_status()}
