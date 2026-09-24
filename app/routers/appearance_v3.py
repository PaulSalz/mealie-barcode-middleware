from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.access_v23 import personal_theme, save_personal_theme
from app.database import get_db
from app.models import SystemState
from app.version import APP_VERSION

router = APIRouter()
_FONT_SIZE_PREFIX = "ui.font_size_percent.user."


def _current_user_id(request: Request) -> int | None:
    value = request.session.get("user_id")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _font_size_key(user_id: int) -> str:
    return f"{_FONT_SIZE_PREFIX}{int(user_id)}"


def _font_size(db: Session, user_id: int) -> int:
    row = db.get(SystemState, _font_size_key(user_id))
    try:
        value = int(float(row.value)) if row and row.value else 100
    except (TypeError, ValueError):
        value = 100
    return max(80, min(120, value))


def _set_font_size(db: Session, user_id: int, value: int) -> None:
    key = _font_size_key(user_id)
    row = db.get(SystemState, key)
    if row:
        row.value = str(value)
    else:
        db.add(SystemState(key=key, value=str(value)))


@router.get("/api/ui-preferences-v3")
def ui_preferences_v3(request: Request, db: Session = Depends(get_db)):
    user_id = _current_user_id(request)
    if user_id is None:
        return JSONResponse({"error": "login required"}, status_code=401)
    theme = personal_theme(db, user_id)
    return {
        "version": APP_VERSION,
        "font_size": _font_size(db, user_id),
        "date_style": theme.get("date_style", "medium"),
    }


@router.post("/api/ui-preferences-v3")
async def save_ui_preferences_v3(request: Request, db: Session = Depends(get_db)):
    user_id = _current_user_id(request)
    if user_id is None:
        return JSONResponse({"error": "login required"}, status_code=401)
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
        _set_font_size(db, user_id, font_size)
        db.commit()

    if "date_style" in body:
        date_style = str(body["date_style"])
        if date_style not in {"short", "medium", "long"}:
            return JSONResponse({"error": "invalid date_style"}, status_code=400)
        save_personal_theme(db, user_id, {"date_style": date_style})

    theme = personal_theme(db, user_id)
    return {
        "ok": True,
        "version": APP_VERSION,
        "font_size": _font_size(db, user_id),
        "date_style": theme.get("date_style", "medium"),
    }
