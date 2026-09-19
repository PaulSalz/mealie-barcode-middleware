import asyncio
from collections import Counter

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.database import get_db
from app.events import scan_events
from app.models import Activity, ApiToken, BarcodeCache, BarcodeMapping, Item, RetryQueue
from app.services.mealie import check_connectivity
from app.templating import _localtime, templates

router = APIRouter()


def _scan_status(result: str, mapping: BarcodeMapping | None) -> str:
    if result == "queued":
        return "queued"
    if result == "unknown":
        return "unknown"
    if result in {"needs_mapping", "error", "broken"}:
        return "pending"
    if mapping:
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
    caches = {
        bc.barcode: bc
        for bc in db.query(BarcodeCache).filter(BarcodeCache.barcode.in_(barcode_ids)).all()
    }
    mappings = {
        m.barcode: m
        for m in db.query(BarcodeMapping).filter(BarcodeMapping.barcode.in_(barcode_ids)).all()
    }

    rows = []
    for activity in activities:
        cached = caches.get(activity.barcode)
        mapping = mappings.get(activity.barcode)
        rows.append({
            "barcode": activity.barcode,
            "title": cached.title if cached and cached.title else activity.message,
            "source": cached.source if cached and cached.source else "—",
            "status": _scan_status(activity.result, mapping),
            "target_name": mapping.target_name if mapping else None,
            "target_id": mapping.target_id if mapping else None,
            "target_type": mapping.target_type if mapping else None,
            "created_at": activity.created_at,
        })
    return rows


def _frequent_targets(db: Session, limit_each: int = 6) -> tuple[list[dict], list[dict]]:
    activities = (
        db.query(Activity)
        .filter(Activity.is_scan_event == True)
        .order_by(Activity.created_at.desc())
        .limit(5000)
        .all()
    )
    if not activities:
        return [], []

    barcodes = list({a.barcode for a in activities})
    mappings = {
        m.barcode: m
        for m in db.query(BarcodeMapping).filter(BarcodeMapping.barcode.in_(barcodes)).all()
    }

    counts: Counter[tuple[str, str, str]] = Counter()
    for activity in activities:
        mapping = mappings.get(activity.barcode)
        if not mapping or mapping.target_type not in {"food", "recipe"}:
            continue
        counts[(mapping.target_type, mapping.target_id, mapping.target_name or mapping.target_id)] += 1

    foods = []
    recipes = []
    for (target_type, target_id, target_name), uses in counts.most_common():
        entry = {"id": target_id, "name": target_name, "uses": uses}
        if target_type == "food" and len(foods) < limit_each:
            foods.append(entry)
        elif target_type == "recipe" and len(recipes) < limit_each:
            recipes.append(entry)
        if len(foods) >= limit_each and len(recipes) >= limit_each:
            break
    return foods, recipes


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    total_barcodes = db.query(BarcodeCache).count()
    mapped_count = db.query(BarcodeMapping).count()
    mapped_sub = db.query(BarcodeMapping.barcode)

    pending_count = (
        db.query(BarcodeCache)
        .filter(BarcodeCache.found == True)
        .filter(~BarcodeCache.barcode.in_(mapped_sub))
        .count()
    )
    queue_depth = db.query(RetryQueue).count()
    unknown_count = (
        db.query(BarcodeCache)
        .filter(BarcodeCache.found == False)
        .filter(~BarcodeCache.barcode.in_(mapped_sub))
        .count()
    )

    recent_items = _recent_scans(db, 25)
    frequent_foods, frequent_recipes = _frequent_targets(db)
    mealie_reachable = check_connectivity()

    last_sync = (
        db.query(Item.synced_at)
        .filter(Item.source == "mealie")
        .order_by(Item.synced_at.desc())
        .first()
    )
    last_sync_time = last_sync[0] if last_sync else None
    has_tokens = db.query(ApiToken).first() is not None

    return templates.TemplateResponse(request, "dashboard.html", {
        "total_barcodes": total_barcodes,
        "mapped_count": mapped_count,
        "pending_count": pending_count,
        "queue_depth": queue_depth,
        "unknown_count": unknown_count,
        "recent_items": recent_items,
        "frequent_foods": frequent_foods,
        "frequent_recipes": frequent_recipes,
        "mealie_reachable": mealie_reachable,
        "last_sync_time": last_sync_time,
        "has_tokens": has_tokens,
    })


@router.get("/api/dashboard")
def dashboard_api(db: Session = Depends(get_db)):
    total_barcodes = db.query(BarcodeCache).count()
    mapped_count = db.query(BarcodeMapping).count()
    mapped_sub = db.query(BarcodeMapping.barcode)
    pending_count = (
        db.query(BarcodeCache)
        .filter(BarcodeCache.found == True)
        .filter(~BarcodeCache.barcode.in_(mapped_sub))
        .count()
    )
    queue_depth = db.query(RetryQueue).count()
    unknown_count = (
        db.query(BarcodeCache)
        .filter(BarcodeCache.found == False)
        .filter(~BarcodeCache.barcode.in_(mapped_sub))
        .count()
    )

    recent_items = _recent_scans(db, 25)

    return {
        "total_barcodes": total_barcodes,
        "mapped_count": mapped_count,
        "pending_count": pending_count,
        "queue_depth": queue_depth,
        "unknown_count": unknown_count,
        "recent_items": [
            {
                "barcode": row["barcode"],
                "item_name": row["target_name"] if row["target_type"] == "food" else None,
                "item_id": row["target_id"] if row["target_type"] == "food" else None,
                "target_type": row["target_type"],
                "title": row["target_name"] if row["target_type"] == "recipe" else (row["title"] or "—"),
                "source": row["source"] or "—",
                "status": row["status"],
                "created_at": _localtime(row["created_at"]),
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
