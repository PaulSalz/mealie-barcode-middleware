import asyncio
from collections import Counter
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.config import settings
from app.database import get_db
from app.events import scan_events
from app.models import Activity, ApiToken, BarcodeCache, BarcodeMapping, Item, RetryQueue
from app.services.mealie import check_connectivity
from app.templating import _localtime, _relative_time, templates
from app.utils import utcnow

router = APIRouter()


def _scan_status(result: str, target_type: str | None) -> str:
    if result == "queued":
        return "queued"
    if result in {"unknown", "unknown_action"}:
        return "unknown"
    if result in {"needs_mapping", "error", "broken", "action_disabled"}:
        return "pending"
    if target_type:
        return "mapped"
    return "pending"


def _recent_scans(db: Session, limit: int = 25) -> list[dict]:
    activities = (
        db.query(Activity)
        .filter(Activity.is_scan_event == True)
        .order_by(Activity.created_at.desc())
        .limit(limit)
        .all()
    )
    if not activities:
        return []

    barcode_ids = list({a.barcode for a in activities})
    caches = {bc.barcode: bc for bc in db.query(BarcodeCache).filter(BarcodeCache.barcode.in_(barcode_ids)).all()}
    mappings = {m.barcode: m for m in db.query(BarcodeMapping).filter(BarcodeMapping.barcode.in_(barcode_ids)).all()}

    rows = []
    for activity in activities:
        cached = caches.get(activity.barcode)
        fallback_mapping = mappings.get(activity.barcode)
        target_type = activity.target_type or (fallback_mapping.target_type if fallback_mapping else None)
        target_id = activity.target_id or (fallback_mapping.target_id if fallback_mapping else None)
        target_name = activity.target_name or (fallback_mapping.target_name if fallback_mapping else None)
        rows.append({
            "barcode": activity.barcode,
            "title": cached.display_title if cached and cached.display_title else activity.message,
            "source": cached.source if cached and cached.source else "—",
            "status": _scan_status(activity.result, target_type),
            "result": activity.result,
            "target_name": target_name,
            "target_id": target_id,
            "target_type": target_type,
            "created_at": activity.created_at,
        })
    return rows


def _frequent_targets(db: Session, limit_each: int = 6) -> tuple[list[dict], list[dict], list[dict]]:
    activities = (
        db.query(Activity)
        .filter(Activity.is_scan_event == True)
        .order_by(Activity.created_at.desc())
        .limit(5000)
        .all()
    )
    if not activities:
        return [], [], []

    barcodes = list({a.barcode for a in activities if not a.target_type})
    mappings = {
        m.barcode: m
        for m in db.query(BarcodeMapping).filter(BarcodeMapping.barcode.in_(barcodes)).all()
    } if barcodes else {}

    counts: Counter[tuple[str, str, str]] = Counter()
    for activity in activities:
        target_type = activity.target_type
        target_id = activity.target_id
        target_name = activity.target_name
        if not target_type:
            mapping = mappings.get(activity.barcode)
            if mapping:
                target_type, target_id, target_name = mapping.target_type, mapping.target_id, mapping.target_name
        if target_type not in {"food", "recipe", "action"} or not target_id:
            continue
        counts[(target_type, target_id, target_name or target_id)] += 1

    foods, recipes, actions = [], [], []
    for (target_type, target_id, target_name), uses in counts.most_common():
        entry = {"id": target_id, "name": target_name, "uses": uses}
        if target_type == "food" and len(foods) < limit_each:
            foods.append(entry)
        elif target_type == "recipe" and len(recipes) < limit_each:
            recipes.append(entry)
        elif target_type == "action" and len(actions) < limit_each:
            actions.append(entry)
        if len(foods) >= limit_each and len(recipes) >= limit_each and len(actions) >= limit_each:
            break
    return foods, recipes, actions


def _summary_counts(db: Session) -> tuple[int, int, int, int, int]:
    total_barcodes = db.query(BarcodeCache).count()
    action_codes = db.query(BarcodeCache).filter(BarcodeCache.source == "action").count()
    mapped_count = db.query(BarcodeMapping).count() + action_codes
    mapped_sub = db.query(BarcodeMapping.barcode)
    pending_count = (
        db.query(BarcodeCache)
        .filter(BarcodeCache.found == True, BarcodeCache.source != "action")
        .filter(~BarcodeCache.barcode.in_(mapped_sub))
        .count()
    )
    queue_depth = db.query(RetryQueue).count()
    unknown_count = (
        db.query(BarcodeCache)
        .filter(BarcodeCache.found == False, BarcodeCache.source != "action")
        .filter(~BarcodeCache.barcode.in_(mapped_sub))
        .count()
    )
    return total_barcodes, mapped_count, pending_count, queue_depth, unknown_count


def _scanner_summary(db: Session) -> tuple[int, int]:
    tokens = db.query(ApiToken).filter(ApiToken.scanner_version.isnot(None)).all()
    cutoff = utcnow().replace(tzinfo=None) - timedelta(minutes=3)
    online = sum(1 for token in tokens if token.scanner_last_seen_at and token.scanner_last_seen_at >= cutoff)
    return online, len(tokens)


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    total_barcodes, mapped_count, pending_count, queue_depth, unknown_count = _summary_counts(db)
    recent_items = _recent_scans(db, 25)
    frequent_foods, frequent_recipes, frequent_actions = _frequent_targets(db)
    mealie_reachable = check_connectivity()
    scanner_online, scanner_total = _scanner_summary(db)

    last_sync = db.query(Item.synced_at).filter(Item.source == "mealie").order_by(Item.synced_at.desc()).first()
    last_sync_time = last_sync[0] if last_sync else None
    has_tokens = db.query(ApiToken).first() is not None
    mealie_url = settings.mealie_url.rstrip("/")
    shopping_list_url = f"{mealie_url}/shopping-lists/{settings.mealie_shopping_list_id}"

    return templates.TemplateResponse(request, "dashboard.html", {
        "total_barcodes": total_barcodes,
        "mapped_count": mapped_count,
        "pending_count": pending_count,
        "queue_depth": queue_depth,
        "unknown_count": unknown_count,
        "recent_items": recent_items,
        "frequent_foods": frequent_foods,
        "frequent_recipes": frequent_recipes,
        "frequent_actions": frequent_actions,
        "mealie_reachable": mealie_reachable,
        "last_sync_time": last_sync_time,
        "has_tokens": has_tokens,
        "mealie_url": mealie_url,
        "shopping_list_url": shopping_list_url,
        "scanner_online": scanner_online,
        "scanner_total": scanner_total,
    })


@router.get("/api/dashboard")
def dashboard_api(db: Session = Depends(get_db)):
    total_barcodes, mapped_count, pending_count, queue_depth, unknown_count = _summary_counts(db)
    recent_items = _recent_scans(db, 25)
    scanner_online, scanner_total = _scanner_summary(db)
    return {
        "total_barcodes": total_barcodes,
        "mapped_count": mapped_count,
        "pending_count": pending_count,
        "queue_depth": queue_depth,
        "unknown_count": unknown_count,
        "scanner_online": scanner_online,
        "scanner_total": scanner_total,
        "recent_items": [
            {
                "barcode": row["barcode"],
                "item_name": row["target_name"] if row["target_type"] == "food" else None,
                "item_id": row["target_id"] if row["target_type"] == "food" else None,
                "target_type": row["target_type"],
                "target_id": row["target_id"],
                "target_name": row["target_name"],
                "title": row["target_name"] if row["target_type"] in {"recipe", "action"} else (row["title"] or "—"),
                "source": row["source"] or "—",
                "status": row["status"],
                "result": row["result"],
                "created_at": _relative_time(row["created_at"]),
                "created_at_absolute": _localtime(row["created_at"]),
            }
            for row in recent_items
        ],
    }


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

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
