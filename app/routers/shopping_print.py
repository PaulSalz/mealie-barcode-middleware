from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.niimblue import is_configured as niim_is_configured, print_image_base64, printer_status
from app.services.shopping import get_default_shopping_list_id, get_shopping_lists
from app.services.shopping_print import (
    load_print_settings,
    save_category_aliases,
    save_category_order,
    save_print_settings,
    shopping_list_payload,
)
from app.templating import templates

router = APIRouter()


@router.get("/shopping-print", response_class=HTMLResponse)
def shopping_print_page(request: Request):
    return templates.TemplateResponse(request, "shopping_print.html", {})


@router.get("/api/shopping-print/bootstrap")
def shopping_print_bootstrap(db: Session = Depends(get_db)):
    lists = get_shopping_lists(force=False)
    try:
        status = printer_status()
    except Exception as exc:
        status = {"configured": niim_is_configured(), "connected": False, "error": str(exc)}
    return {
        "lists": lists,
        "default_list_id": get_default_shopping_list_id(db),
        "settings": load_print_settings(db),
        "printer": status,
    }


@router.get("/api/shopping-print/lists/{list_id}")
def shopping_print_list(list_id: str, db: Session = Depends(get_db)):
    try:
        return shopping_list_payload(db, list_id)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.post("/api/shopping-print/settings")
async def shopping_print_save_settings(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)
    try:
        saved = save_print_settings(db, body)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {"ok": True, "settings": saved}


@router.post("/api/shopping-print/category-order")
async def shopping_print_save_category_order(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)
    list_id = str(body.get("list_id") or "").strip()
    order = body.get("category_order")
    aliases = body.get("category_aliases", {})
    if not isinstance(order, list):
        return JSONResponse({"error": "category_order array required"}, status_code=400)
    if not isinstance(aliases, dict):
        return JSONResponse({"error": "category_aliases object required"}, status_code=400)
    available = {str(row.get("id")) for row in get_shopping_lists(force=False)}
    if not list_id or list_id not in available:
        return JSONResponse({"error": "Shopping list not found"}, status_code=404)
    try:
        saved_order = save_category_order(db, list_id, order)
        saved_aliases = save_category_aliases(db, list_id, aliases)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {
        "ok": True,
        "list_id": list_id,
        "category_order": saved_order,
        "category_aliases": saved_aliases,
    }


@router.post("/api/shopping-print/print")
async def shopping_print_print(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)

    image_base64 = str(body.get("image_base64") or "")
    if image_base64.startswith("data:") and "," in image_base64:
        image_base64 = image_base64.split(",", 1)[1]
    if not image_base64:
        return JSONResponse({"error": "Rendered shopping-list image is required"}, status_code=400)
    if len(image_base64) > 24_000_000:
        return JSONResponse({"error": "Rendered shopping list is too large"}, status_code=413)

    try:
        height_mm = float(body.get("height_mm"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "Invalid rendered paper height"}, status_code=400)
    if not 5 <= height_mm <= 1000:
        return JSONResponse({"error": "Rendered paper height must be between 5 and 1000 mm"}, status_code=400)
    if not niim_is_configured():
        return JSONResponse({"error": "NIIMBOT printing is not configured"}, status_code=400)

    cfg = load_print_settings(db)
    try:
        result = print_image_base64(
            image_base64,
            width_mm=cfg["paper_width_mm"],
            height_mm=height_mm,
            quantity=1,
            density=cfg["density"],
            label_type=cfg["label_type"],
            dpi=cfg["dpi"],
            threshold=cfg["threshold"],
        )
        return {"ok": True, "height_mm": round(height_mm, 1), **result}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
