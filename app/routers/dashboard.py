import asyncio
import json
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.config import settings
from app.database import get_db
from app.events import scan_events
from app.models import Action, Activity, ApiToken, BarcodeCache, BarcodeTarget, Item, RetryQueue, SystemState
from app.services.mealie_health import mealie_reachable
from app.services.actions import execute_action
from app.services.scan_stats import frequent_targets as frequent_target_stats
from app.services.shopping import (
    add_food_to_list, add_note_to_list, add_recipe_to_list,
    get_default_shopping_list_id, get_shopping_list_counts, get_shopping_lists,
)
from app.services.targets import primary_targets_by_barcode
from app.templating import _localtime, _relative_time, templates
from app.utils import utcnow

router = APIRouter()

_FREQUENT_USED_LIMITS = (3, 6, 9, 12, 15, 20)
_FREQUENT_USED_LIMIT_KEY = "appearance.v35.user.{}.frequent_used_limit"


def _frequent_used_limit(db: Session, user_id) -> int:
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return 6
    row = db.get(SystemState, _FREQUENT_USED_LIMIT_KEY.format(user_id))
    try:
        value = int(row.value) if row and row.value else 6
    except (TypeError, ValueError):
        value = 6
    return value if value in _FREQUENT_USED_LIMITS else 6


def _scan_status(result: str, target_type: str | None) -> str:
    if result == "queued": return "queued"
    if result in {"unknown", "unknown_action"}: return "unknown"
    if result in {"needs_mapping", "error", "partial", "broken", "action_disabled"}: return "pending"
    if target_type: return "mapped"
    return "pending"


def _activity_targets(activity: Activity, fallback=None) -> list[dict]:
    if activity.targets_json:
        try:
            rows = json.loads(activity.targets_json)
            if isinstance(rows, list) and rows:
                return [row for row in rows if isinstance(row, dict)]
        except (TypeError, ValueError):
            pass
    if activity.target_type and activity.target_id:
        return [{"type": activity.target_type, "id": activity.target_id, "name": activity.target_name}]
    if fallback:
        return [{"type": fallback.target_type, "id": fallback.target_id, "name": fallback.target_name}]
    return []


def _recent_scans(db: Session, limit: int = 25) -> list[dict]:
    activities = db.query(Activity).filter(Activity.is_scan_event == True).order_by(Activity.created_at.desc()).limit(limit).all()
    if not activities: return []
    barcode_ids = list({a.barcode for a in activities})
    caches = {bc.barcode: bc for bc in db.query(BarcodeCache).filter(BarcodeCache.barcode.in_(barcode_ids)).all()}
    primaries = primary_targets_by_barcode(db, barcode_ids)
    rows = []
    for activity in activities:
        cached = caches.get(activity.barcode)
        targets = _activity_targets(activity, primaries.get(activity.barcode))
        first = targets[0] if targets else {}
        target_name = activity.target_name or first.get("name")
        rows.append({
            "barcode": activity.barcode,
            "title": cached.display_title if cached and cached.display_title else activity.message,
            "source": cached.source if cached and cached.source else "—",
            "status": _scan_status(activity.result, first.get("type") or activity.target_type),
            "result": activity.result,
            "target_name": target_name,
            "target_id": first.get("id") or activity.target_id,
            "target_type": first.get("type") or activity.target_type,
            "target_count": len(targets),
            "created_at": activity.created_at,
        })
    return rows


def _frequent_targets(db: Session, limit_each: int = 6) -> tuple[list[dict], list[dict], list[dict]]:
    return (
        frequent_target_stats(db, "food", limit_each),
        frequent_target_stats(db, "recipe", limit_each),
        frequent_target_stats(db, "action", limit_each),
    )


def _summary_counts(db: Session) -> tuple[int, int, int, int, int]:
    total_barcodes = db.query(BarcodeCache).count()
    mapped_sub = db.query(BarcodeTarget.barcode).filter(BarcodeTarget.enabled == True).distinct()
    mapped_target_count = db.query(BarcodeTarget.barcode).filter(BarcodeTarget.enabled == True).distinct().count()
    action_codes = db.query(BarcodeCache).filter(
        BarcodeCache.source == "action",
        ~BarcodeCache.barcode.in_(mapped_sub),
    ).count()
    mapped_count = mapped_target_count + action_codes
    pending_count = db.query(BarcodeCache).filter(BarcodeCache.found == True, BarcodeCache.source != "action", ~BarcodeCache.barcode.in_(mapped_sub)).count()
    queue_depth = db.query(RetryQueue).count()
    unknown_count = db.query(BarcodeCache).filter(BarcodeCache.found == False, BarcodeCache.source != "action", ~BarcodeCache.barcode.in_(mapped_sub)).count()
    return total_barcodes, mapped_count, pending_count, queue_depth, unknown_count


def _scanner_summary(db: Session) -> tuple[int, int]:
    tokens = db.query(ApiToken).filter(ApiToken.scanner_version.isnot(None)).all()
    cutoff = utcnow().replace(tzinfo=None) - timedelta(minutes=3)
    disconnected_values = {"", "disconnected", "none", "offline", "unknown"}
    connected = 0
    for token in tokens:
        bridge_online = bool(token.scanner_last_seen_at and token.scanner_last_seen_at >= cutoff)
        device = (token.scanner_device or "").strip().casefold()
        if bridge_online and device not in disconnected_values:
            connected += 1
    return connected, len(tokens)


def _readiness_issues(*, mealie_reachable: bool, has_tokens: bool, scanner_online: int, scanner_total: int, default_list_id: str | None, queue_depth: int) -> list[dict]:
    issues: list[dict] = []
    if not mealie_reachable:
        issues.append({"severity": "danger", "icon": "plug-connected-x", "title": "Mealie is not reachable", "message": "B2M cannot read or update your shopping lists right now.", "href": "/settings?tab=mealie", "action": "Check Mealie connection"})
    if not default_list_id:
        issues.append({"severity": "warning", "icon": "list-check", "title": "No default shopping list is selected", "message": "Choose which Mealie list should receive scans when no list is specified.", "href": "/settings?tab=mealie", "action": "Choose shopping list"})
    if not has_tokens:
        issues.append({"severity": "warning", "icon": "key", "title": "No scanner access token exists", "message": "Create one token before connecting a physical barcode scanner.", "href": "/settings?tab=tokens", "action": "Create scanner token"})
    elif scanner_total == 0:
        issues.append({"severity": "warning", "icon": "scan", "title": "No scanner has connected yet", "message": "B2M is ready for a scanner, but no scanner bridge has reported in yet.", "href": "/settings?tab=scanning", "action": "Open scanner setup"})
    elif scanner_online == 0:
        issues.append({"severity": "warning", "icon": "scan-eye", "title": "Your scanner is offline", "message": "A scanner is configured, but B2M has not seen it recently.", "href": "/settings?tab=scanning", "action": "Check scanner"})
    if queue_depth:
        issues.append({"severity": "warning", "icon": "refresh", "title": f"{queue_depth} scan{'s are' if queue_depth != 1 else ' is'} waiting for retry", "message": "Nothing is lost. B2M will retry automatically when Mealie is available.", "href": "/activities?result=queued", "action": "View queued scans"})
    return issues


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    total_barcodes, mapped_count, pending_count, queue_depth, unknown_count = _summary_counts(db)
    recent_items = _recent_scans(db, 25)
    frequent_limit = _frequent_used_limit(db, request.session.get("user_id"))
    frequent_foods, frequent_recipes, frequent_actions = _frequent_targets(db, limit_each=frequent_limit)
    reachable = mealie_reachable()
    scanner_online, scanner_total = _scanner_summary(db)
    last_sync = db.query(Item.synced_at).filter(Item.source == "mealie").order_by(Item.synced_at.desc()).first()
    last_sync_time = last_sync[0] if last_sync else None
    mealie_url = settings.mealie_url.rstrip("/")
    default_list_id = get_default_shopping_list_id(db)
    shopping_list_url = f"{mealie_url}/shopping-lists/{default_list_id}" if default_list_id else f"{mealie_url}/shopping-lists"
    shopping_lists_status = get_shopping_list_counts()
    has_tokens = db.query(ApiToken).first() is not None
    readiness_issues = _readiness_issues(mealie_reachable=reachable, has_tokens=has_tokens, scanner_online=scanner_online, scanner_total=scanner_total, default_list_id=default_list_id, queue_depth=queue_depth)
    return templates.TemplateResponse(request, "dashboard.html", {
        "total_barcodes": total_barcodes, "mapped_count": mapped_count,
        "pending_count": pending_count, "queue_depth": queue_depth, "unknown_count": unknown_count,
        "recent_items": recent_items,
        "frequent_foods": frequent_foods, "frequent_recipes": frequent_recipes, "frequent_actions": frequent_actions,
        "frequent_used_limit": frequent_limit,
        "mealie_reachable": reachable, "last_sync_time": last_sync_time,
        "has_tokens": has_tokens,
        "mealie_url": mealie_url, "shopping_list_url": shopping_list_url,
        "shopping_lists_status": shopping_lists_status,
        "scanner_online": scanner_online, "scanner_total": scanner_total,
        "readiness_issues": readiness_issues, "system_ready": not readiness_issues,
        "dashboard_poll_interval_seconds": settings.dashboard_poll_interval_seconds,
        "health_poll_interval_seconds": settings.health_poll_interval_seconds,
    })


@router.get("/api/dashboard")
def dashboard_api(db: Session = Depends(get_db)):
    total_barcodes, mapped_count, pending_count, queue_depth, unknown_count = _summary_counts(db)
    recent_items = _recent_scans(db, 25)
    scanner_online, scanner_total = _scanner_summary(db)
    return {
        "total_barcodes": total_barcodes, "mapped_count": mapped_count,
        "pending_count": pending_count, "queue_depth": queue_depth, "unknown_count": unknown_count,
        "scanner_online": scanner_online, "scanner_total": scanner_total,
        "shopping_lists": get_shopping_list_counts(),
        "poll_interval_seconds": settings.dashboard_poll_interval_seconds,
        "recent_items": [{
            "barcode": row["barcode"], "product_name": row["title"] or "—",
            "item_name": row["target_name"] if row["target_type"] == "food" else None,
            "item_id": row["target_id"] if row["target_type"] == "food" else None,
            "target_type": row["target_type"], "target_id": row["target_id"], "target_name": row["target_name"],
            "target_count": row.get("target_count", 0),
            "title": row["target_name"] if row["target_type"] in {"recipe", "action"} else (row["title"] or "—"),
            "source": row["source"] or "—", "status": row["status"], "result": row["result"],
            "created_at": _relative_time(row["created_at"]), "created_at_absolute": _localtime(row["created_at"]),
        } for row in recent_items],
    }


@router.get("/api/dashboard/frequent")
def dashboard_frequent_api(request: Request, db: Session = Depends(get_db)):
    limit = _frequent_used_limit(db, request.session.get("user_id"))
    return {
        "foods": frequent_target_stats(db, "food", limit),
        "recipes": frequent_target_stats(db, "recipe", limit),
        "actions": frequent_target_stats(db, "action", limit),
        "limit": limit,
    }


@router.post("/api/dashboard/frequent/actions/{action_id}/trigger")
def dashboard_frequent_action_trigger(
    action_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    action = db.get(Action, action_id)
    if not action:
        return JSONResponse({"error": "Action not found"}, status_code=404)
    if not action.enabled:
        return JSONResponse({"error": "This action is disabled"}, status_code=409)

    barcode = f"ACTION:{action.id}"
    if action.execution_mode == "async":
        background_tasks.add_task(execute_action, action.id, barcode)
        return JSONResponse({"ok": True, "status": "queued", "action_id": action.id, "action_name": action.name}, status_code=202)

    result = execute_action(action.id, barcode)
    status = result.get("status")
    if status == "success":
        return {"ok": True, **result}
    if status == "ignored_cooldown":
        return JSONResponse({"error": "This action is cooling down. Try again shortly.", **result}, status_code=409)
    return JSONResponse({"error": result.get("error") or "Action could not be triggered", **result}, status_code=502)


@router.post("/api/dashboard/frequent/add")
async def dashboard_frequent_add(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
    except (ValueError, TypeError):
        return JSONResponse({"error": "Invalid request body"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)

    target_type = str(body.get("target_type") or "").strip().lower()
    target_id = str(body.get("target_id") or "").strip()
    list_id = str(body.get("list_id") or "").strip()
    try:
        quantity = float(body.get("quantity", 1))
    except (TypeError, ValueError):
        return JSONResponse({"error": "Enter a valid quantity"}, status_code=400)
    if not target_id or not list_id:
        return JSONResponse({"error": "Choose an item and shopping list"}, status_code=400)
    if not 0.01 <= quantity <= 1000:
        return JSONResponse({"error": "Quantity must be between 0.01 and 1000"}, status_code=400)

    lists = get_shopping_lists()
    selected_list = next((row for row in lists if str(row.get("id")) == list_id), None)
    if not selected_list:
        return JSONResponse({"error": "Shopping list not found"}, status_code=404)

    if target_type == "food":
        item = db.get(Item, target_id)
        if not item:
            return JSONResponse({"error": "Food not found"}, status_code=404)
        if item.source == "mealie":
            ok = add_food_to_list(item.id, quantity, None, list_id)
        else:
            ok = add_note_to_list(item.name, list_id, quantity)
    elif target_type == "recipe":
        ok = add_recipe_to_list(target_id, quantity, list_id)
    else:
        return JSONResponse({"error": "Only foods and recipes can be added from this section"}, status_code=400)

    if not ok:
        return JSONResponse({"error": "Mealie could not add this item to the selected list"}, status_code=502)
    return {"ok": True, "list_id": list_id, "list_name": selected_list.get("name") or "Shopping list", "quantity": quantity}


@router.get("/events")
async def sse_stream():
    queue = scan_events.subscribe()
    async def _generate():
        try:
            yield ": connected\n\n"
            while True:
                yield await queue.get()
        except asyncio.CancelledError:
            pass
        finally:
            scan_events.unsubscribe(queue)
    return StreamingResponse(_generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
