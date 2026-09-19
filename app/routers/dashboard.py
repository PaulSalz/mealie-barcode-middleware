import asyncio

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.database import get_db
from app.events import scan_events
from app.models import ApiToken, BarcodeCache, BarcodeMapping, Item, RetryQueue
from app.services.mealie import check_connectivity
from app.templating import _localtime, templates

router = APIRouter()


def _recent_rows(db: Session, recent: list[BarcodeCache]) -> list[dict]:
    recent_barcodes = [bc.barcode for bc in recent]
    mappings = (
        {
            m.barcode: m
            for m in db.query(BarcodeMapping)
            .filter(BarcodeMapping.barcode.in_(recent_barcodes))
            .all()
        }
        if recent_barcodes
        else {}
    )
    queued_barcodes = (
        {
            row.barcode
            for row in db.query(RetryQueue)
            .filter(RetryQueue.barcode.in_(recent_barcodes))
            .all()
        }
        if recent_barcodes
        else set()
    )

    food_ids = [m.target_id for m in mappings.values() if m.target_type == "food"]
    foods = (
        {item.id: item for item in db.query(Item).filter(Item.id.in_(food_ids)).all()}
        if food_ids
        else {}
    )

    result = []
    for bc in recent:
        mapping = mappings.get(bc.barcode)
        if mapping:
            status = "mapped"
            item = foods.get(mapping.target_id) if mapping.target_type == "food" else None
            target_name = mapping.target_name
            target_type = mapping.target_type
            target_id = mapping.target_id
        else:
            item = None
            target_name = None
            target_type = None
            target_id = None
            if bc.barcode in queued_barcodes:
                status = "queued"
            elif not bc.found:
                status = "unknown"
            else:
                status = "pending"

        result.append({
            "barcode": bc,
            "status": status,
            "item": item,
            "target_name": target_name,
            "target_type": target_type,
            "target_id": target_id,
        })
    return result


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

    recent = db.query(BarcodeCache).order_by(BarcodeCache.created_at.desc()).limit(10).all()
    recent_items = _recent_rows(db, recent)
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

    recent = db.query(BarcodeCache).order_by(BarcodeCache.created_at.desc()).limit(10).all()
    recent_items = _recent_rows(db, recent)

    return {
        "total_barcodes": total_barcodes,
        "mapped_count": mapped_count,
        "pending_count": pending_count,
        "queue_depth": queue_depth,
        "unknown_count": unknown_count,
        "recent_items": [
            {
                "barcode": row["barcode"].barcode,
                "item_name": row["target_name"] or (row["item"].name if row["item"] else None),
                "item_id": row["target_id"],
                "target_type": row["target_type"],
                "title": row["barcode"].title or "—",
                "source": row["barcode"].source or "—",
                "status": row["status"],
                "created_at": _localtime(row["barcode"].created_at),
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
