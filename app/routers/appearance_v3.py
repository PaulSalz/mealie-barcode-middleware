from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import SystemState
from app.templating import set_cached_theme
from app.theme import get_theme, save_theme
from app.version import APP_VERSION

router = APIRouter()
_FONT_SIZE_KEY = "ui.font_size_percent"


def _font_size(db: Session) -> int:
    row = db.get(SystemState, _FONT_SIZE_KEY)
    try:
        value = int(float(row.value)) if row and row.value else 100
    except (TypeError, ValueError):
        value = 100
    return max(80, min(120, value))


def _set_font_size(db: Session, value: int) -> None:
    row = db.get(SystemState, _FONT_SIZE_KEY)
    if row:
        row.value = str(value)
    else:
        db.add(SystemState(key=_FONT_SIZE_KEY, value=str(value)))


def _require_admin(request: Request):
    if not request.session.get("is_admin", False):
        return JSONResponse({"error": "admin required"}, status_code=403)
    return None


@router.get("/api/ui-preferences-v3")
def ui_preferences_v3(db: Session = Depends(get_db)):
    theme = get_theme(db)
    return {
        "version": APP_VERSION,
        "font_size": _font_size(db),
        "date_style": theme.get("date_style", "medium"),
    }


@router.post("/api/ui-preferences-v3")
async def save_ui_preferences_v3(request: Request, db: Session = Depends(get_db)):
    if denied := _require_admin(request):
        return denied

    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)

    if "font_size" in body:
        try:
            font_size = int(float(body["font_size"]))
        except (TypeError, ValueError):
            return JSONResponse({"error": "font_size must be numeric"}, status_code=400)
        if not 80 <= font_size <= 120:
            return JSONResponse({"error": "font_size must be between 80 and 120"}, status_code=400)
        _set_font_size(db, font_size)
        db.commit()

    if "date_style" in body:
        date_style = str(body["date_style"])
        if date_style not in {"short", "medium", "long"}:
            return JSONResponse({"error": "invalid date_style"}, status_code=400)
        save_theme(db, {"date_style": date_style})
        set_cached_theme(get_theme(db))

    theme = get_theme(db)
    return {
        "ok": True,
        "version": APP_VERSION,
        "font_size": _font_size(db),
        "date_style": theme.get("date_style", "medium"),
    }
