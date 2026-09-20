import io
import json
import logging
import re

import barcode as barcode_lib
import segno
from barcode.writer import SVGWriter
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Action, BarcodeCache, BarcodeMapping, Item
from app.services.fuzzy import fuzzy_match
from app.services.niimblue import is_configured as niim_is_configured
from app.services.niimblue import print_image_base64, printer_status
from app.templating import templates
from app.utils import utcnow

logger = logging.getLogger(__name__)
router = APIRouter()
_ACTION_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,96}$")

GENERIC_EXAMPLES = [
    "Brot", "Brötchen", "Milch", "Eier", "Butter", "Reis", "Nudeln",
    "Mehl", "Zucker", "Kaffee", "Tee", "Kartoffeln", "Zwiebeln",
]
RECIPE_EXAMPLES = [
    "Pizza", "Pfannkuchen", "Pasta", "Lasagne", "Curry", "Chili",
    "Salat", "Suppe", "Burger", "Wraps",
]


def _prefill(request: Request, db: Session) -> dict | None:
    food_id = request.query_params.get("food")
    action_id = request.query_params.get("action")
    raw_code = request.query_params.get("code")

    if food_id:
        item = db.get(Item, food_id)
        if item:
            return {
                "code": f"FOOD:{item.id}",
                "label": item.name,
                "target_type": "food",
                "target_id": item.id,
                "target_name": item.name,
                "kind": "auto",
            }
    if action_id:
        action = db.get(Action, action_id)
        if action:
            return {
                "code": f"ACTION:{action.id}",
                "label": action.name,
                "target_type": "action",
                "target_id": action.id,
                "target_name": action.name,
                "kind": "auto",
            }
    if raw_code:
        cached = db.get(BarcodeCache, raw_code)
        mapping = db.get(BarcodeMapping, raw_code)
        return {
            "code": raw_code,
            "label": (cached.display_title if cached else None) or raw_code,
            "target_type": mapping.target_type if mapping else "custom",
            "target_id": mapping.target_id if mapping else "",
            "target_name": mapping.target_name if mapping else "",
            "kind": "auto",
        }
    return None


@router.get("/labels", response_class=HTMLResponse)
def labels_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "labels.html", {
        "generic_examples": GENERIC_EXAMPLES,
        "recipe_examples": RECIPE_EXAMPLES,
        "prefill": _prefill(request, db),
        "default_action_webhook": settings.ha_webhook_url,
        "niim_configured": niim_is_configured(),
    })


def _qr_svg(value: str) -> bytes:
    """Render a QR SVG with intrinsic dimensions intact.

    Keeping Segno's native width/height is important when the SVG is loaded through
    an <img>: replacing them with only a viewBox can leave the image without a usable
    intrinsic size in some browser/flex layouts.
    """
    qr = segno.make(value, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=4, border=2, xmldecl=False)
    return buf.getvalue()


def _linear_svg(kind: str, value: str) -> bytes:
    value = value.strip()
    if kind == "code128":
        try:
            value.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("Code 128 needs an ASCII-safe value. Use Auto/QR, or percent-encode the text.") from exc
        cls = barcode_lib.get_barcode_class("code128")
        code_value = value
    elif kind == "ean13":
        if not value.isdigit() or len(value) not in (12, 13):
            raise ValueError("EAN-13 only works with 12 or 13 digits")
        cls = barcode_lib.get_barcode_class("ean13")
        code_value = value[:12]
    elif kind == "upca":
        if not value.isdigit() or len(value) not in (11, 12):
            raise ValueError("UPC-A only works with 11 or 12 digits")
        cls = barcode_lib.get_barcode_class("upca")
        code_value = value[:11]
    else:
        raise ValueError("Unsupported symbology")

    buf = io.BytesIO()
    code = cls(code_value, writer=SVGWriter())
    code.write(buf, options={
        "write_text": False,
        "quiet_zone": 2.0,
        "module_height": 12.0,
        "font_size": 0,
    })
    return buf.getvalue()


def _auto_kind(value: str) -> str:
    """Prefer Code 128 for compact ASCII IDs; use QR for long or Unicode values."""
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        return "qr"
    return "code128" if len(value) <= 32 else "qr"


@router.get("/labels/code.svg")
def generate_code_svg(
    value: str = Query(..., min_length=1, max_length=256),
    kind: str = Query("auto"),
):
    kind = kind.lower().strip()
    if kind == "auto":
        kind = _auto_kind(value)
    try:
        content = _qr_svg(value) if kind == "qr" else _linear_svg(kind, value)
    except (ValueError, barcode_lib.errors.BarcodeError) as exc:
        return Response(content=str(exc), status_code=422, media_type="text/plain")
    return Response(content=content, media_type="image/svg+xml", headers={"X-Code-Kind": kind})


# Backward-compatible endpoint for old bookmarks / JS.
@router.get("/labels/qr.svg")
def generate_qr_svg(text: str = Query(..., min_length=1)):
    return Response(content=_qr_svg(f"GENERIC:{text}"), media_type="image/svg+xml")


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


@router.get("/labels/actions-search")
def labels_search_actions(q: str = Query(default=""), db: Session = Depends(get_db)):
    query = db.query(Action).filter(Action.enabled == True)
    q = q.strip()
    if q:
        query = query.filter(Action.name.ilike(f"%{q}%") | Action.id.ilike(f"%{q}%"))
    actions = query.order_by(Action.name).limit(20).all()
    return [{"id": a.id, "name": a.name, "code": f"ACTION:{a.id}"} for a in actions]


@router.post("/labels/actions-create")
async def labels_create_action(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    action_id = str(body.get("id") or "").strip()
    name = str(body.get("name") or action_id).strip()
    webhook_url = str(body.get("webhook_url") or settings.ha_webhook_url or "").strip()
    if not _ACTION_ID_RE.fullmatch(action_id):
        return JSONResponse({"error": "ID may contain letters, numbers, dot, dash and underscore."}, status_code=400)
    if db.get(Action, action_id):
        return JSONResponse({"error": "An Action with this ID already exists."}, status_code=409)
    if not webhook_url:
        return JSONResponse({"error": "A webhook URL is required."}, status_code=400)
    try:
        duration_seconds = max(0, int(body.get("duration_seconds") or 0))
        cooldown = max(0.0, float(str(body.get("cooldown_seconds") or "2").replace(",", ".")))
    except (TypeError, ValueError):
        return JSONResponse({"error": "Invalid duration or cooldown."}, status_code=400)

    params = {"duration_seconds": duration_seconds} if duration_seconds else {}
    payload = {
        "action_id": "{{ action.id }}",
        "action_name": "{{ action.name }}",
        "barcode": "{{ scan.barcode }}",
        "params": "{{ params }}",
    }
    action = Action(
        id=action_id,
        name=name or action_id,
        description="Created from Code Generator",
        aliases_json="[]",
        enabled=True,
        action_type="webhook",
        webhook_url=webhook_url,
        method="POST",
        headers_json="{}",
        payload_json=json.dumps(payload),
        parameters_json=json.dumps(params),
        connect_timeout=2.0,
        read_timeout=5.0,
        write_timeout=5.0,
        pool_timeout=2.0,
        retries=0,
        retry_delay=0.5,
        backoff_factor=2.0,
        retry_policy="network",
        cooldown_seconds=cooldown,
        execution_mode="async",
        respect_pause=False,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(action)
    db.commit()
    return {"id": action.id, "name": action.name, "code": f"ACTION:{action.id}"}


@router.get("/labels/fuzzy")
def labels_fuzzy_match(q: str = Query(default=""), db: Session = Depends(get_db)):
    q = q.strip()
    if not q:
        return {"candidates": []}
    candidates = fuzzy_match(q, None, db)
    top = [c for c in candidates[:5] if c["score"] >= 60]
    return {"candidates": [{"id": c["item_id"], "name": c["item_name"], "score": c["score"]} for c in top]}


def _upsert_cache(code: str, label: str, source: str, db: Session) -> BarcodeCache:
    cached = db.get(BarcodeCache, code)
    now = utcnow()
    if not cached:
        cached = BarcodeCache(
            barcode=code,
            source=source,
            title=label or code,
            custom_title=label or None,
            found=True,
            lookup_attempted_at=now,
            created_at=now,
        )
        db.add(cached)
    else:
        if label:
            cached.custom_title = label
        if source in {"generator", "action", "generic"}:
            cached.source = source
        cached.found = True
    return cached


@router.post("/labels/register", response_class=JSONResponse)
async def register_labels_batch(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    labels = body.get("labels", [])
    if not isinstance(labels, list) or not labels:
        return JSONResponse({"error": "labels array is required"}, status_code=400)

    registered = 0
    mapped = 0
    errors = []
    for entry in labels:
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("code") or "").strip()
        label = str(entry.get("label") or code).strip()
        target_type = str(entry.get("target_type") or "custom").strip().lower()
        target_id = str(entry.get("target_id") or "").strip()
        target_name = str(entry.get("target_name") or label).strip()
        if not code or len(code) > 256:
            errors.append(f"Invalid code: {code[:40]}")
            continue

        source = "action" if target_type == "action" else "generic" if code.upper().startswith("GENERIC:") else "generator"
        existed = db.get(BarcodeCache, code) is not None
        _upsert_cache(code, label, source, db)
        if not existed:
            registered += 1

        if target_type in {"food", "recipe"} and target_id:
            mapping = db.get(BarcodeMapping, code)
            if not mapping:
                mapping = BarcodeMapping(barcode=code, target_type=target_type, target_id=target_id)
                db.add(mapping)
            mapping.target_type = target_type
            mapping.target_id = target_id
            mapping.target_name = target_name or target_id
            mapping.quantity = 1.0
            mapping.unit_id = None
            mapping.recipe_scale = 1.0
            mapping.mapped_by = "manual"
            mapped += 1
        elif target_type == "action":
            if not target_id or not db.get(Action, target_id):
                errors.append(f"Action not found for {code}")
            elif code != f"ACTION:{target_id}":
                errors.append(f"Action code must remain ACTION:{target_id}")

    db.commit()
    return {"registered": registered, "mapped": mapped, "total": len(labels), "errors": errors}


@router.get("/labels/printer-status")
def labels_printer_status():
    return printer_status()


@router.post("/labels/niim-print")
async def labels_niim_print(request: Request):
    body = await request.json()
    image_base64 = str(body.get("image_base64") or "")
    if image_base64.startswith("data:") and "," in image_base64:
        image_base64 = image_base64.split(",", 1)[1]
    if not image_base64:
        return JSONResponse({"error": "Rendered label image is required."}, status_code=400)
    try:
        width_mm = float(body.get("width_mm"))
        height_mm = float(body.get("height_mm"))
        quantity = int(body.get("quantity") or 1)
        result = print_image_base64(
            image_base64,
            width_mm=width_mm,
            height_mm=height_mm,
            quantity=quantity,
        )
        return result
    except Exception as exc:
        logger.exception("NIIMBOT print failed")
        return JSONResponse({"error": str(exc)}, status_code=502)
