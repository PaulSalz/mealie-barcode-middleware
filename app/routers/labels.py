import io
import logging

import segno
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BarcodeCache, BarcodeMapping, Item
from app.services.fuzzy import fuzzy_match
from app.templating import templates
from app.utils import utcnow

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/labels", response_class=HTMLResponse)
def labels_page(request: Request):
    return templates.TemplateResponse(request, "labels.html", {})


@router.get("/labels/qr.svg")
def generate_qr_svg(text: str = Query(..., min_length=1)):
    """Generate a QR code SVG for GENERIC:{text}."""
    import re

    content = f"GENERIC:{text}"
    qr = segno.make(content, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=1, border=2, xmldecl=False)
    svg = buf.getvalue().decode()

    def _to_viewbox(m):
        return f'viewBox="0 0 {m.group(1)} {m.group(2)}"'

    svg = re.sub(r'width="(\d+)" height="(\d+)"', _to_viewbox, svg, count=1)
    return Response(content=svg.encode(), media_type="image/svg+xml")


@router.get("/labels/search")
def labels_search_items(q: str = Query(default=""), db: Session = Depends(get_db)):
    q = q.strip()
    if not q:
        return []
    words = [w for w in q.split() if len(w) >= 2] or [q]
    conditions = [Item.name.ilike(f"%{word}%") for word in words]
    items = (
        db.query(Item)
        .filter(Item.source == "mealie", or_(*conditions))
        .order_by(Item.name)
        .limit(20)
        .all()
    )
    return [{"id": i.id, "name": i.name, "source": i.source} for i in items]


@router.get("/labels/fuzzy")
def labels_fuzzy_match(q: str = Query(default=""), db: Session = Depends(get_db)):
    q = q.strip()
    if not q:
        return {"candidates": []}
    candidates = fuzzy_match(q, None, db)
    top = [c for c in candidates[:5] if c["score"] >= 60]
    return {
        "candidates": [
            {"id": c["item_id"], "name": c["item_name"], "score": c["score"]}
            for c in top
        ],
    }


@router.post("/labels/register", response_class=JSONResponse)
async def register_labels_batch(request: Request, db: Session = Depends(get_db)):
    """Register GENERIC labels and optionally link them to real Mealie Foods."""
    body = await request.json()
    labels = body.get("labels", [])
    if not labels:
        return JSONResponse({"error": "labels array is required"}, status_code=400)

    registered = 0
    mapped = 0

    for entry in labels:
        text = entry.get("text", "").strip()
        item_id = entry.get("item_id")
        if not text:
            continue

        barcode = f"GENERIC:{text}"
        existing_cache = db.get(BarcodeCache, barcode)
        if not existing_cache:
            db.add(BarcodeCache(
                barcode=barcode,
                source="generic",
                title=text,
                found=True,
                lookup_attempted_at=utcnow(),
            ))
            registered += 1

        if item_id:
            item = db.get(Item, item_id)
            if item and item.source == "mealie":
                mapping = db.get(BarcodeMapping, barcode)
                if not mapping:
                    mapping = BarcodeMapping(
                        barcode=barcode,
                        target_type="food",
                        target_id=item.id,
                    )
                    db.add(mapping)
                mapping.target_type = "food"
                mapping.target_id = item.id
                mapping.target_name = item.name
                mapping.quantity = 1.0
                mapping.unit_id = None
                mapping.recipe_scale = 1.0
                mapping.mapped_by = "manual"
                mapped += 1

    db.commit()
    return {"registered": registered, "mapped": mapped, "total": len(labels)}
