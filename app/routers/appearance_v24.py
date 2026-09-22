from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.access_v23 import (
    RAINBOW_BUTTON_CHOICES,
    RAINBOW_BUTTON_DEFAULT,
    personal_theme,
    rainbow_button_key,
    rainbow_button_preference,
)
from app.database import get_db
from app.models import SystemState
from app.theme import COLOR_CSS, THEME_CHOICES, THEME_DEFAULTS, build_theme_css

router = APIRouter()


def _current_user_id(request: Request) -> int | None:
    value = request.session.get("user_id")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _preview_theme(current: dict[str, str], body: dict) -> dict[str, str]:
    theme = dict(current)
    for key, default in THEME_DEFAULTS.items():
        if key not in body:
            continue
        value = str(body.get(key, default))
        if key in THEME_CHOICES and value not in THEME_CHOICES[key]:
            value = default
        if key == "contrast":
            try:
                value = str(max(0, min(100, int(float(value)))))
            except (TypeError, ValueError):
                value = default
        theme[key] = value
    return theme


@router.get("/api/appearance-v24")
def appearance_v24_get(request: Request, db: Session = Depends(get_db)):
    user_id = _current_user_id(request)
    if user_id is None:
        return JSONResponse({"error": "login required"}, status_code=401)
    return {
        "rainbow_buttons": rainbow_button_preference(db, user_id),
        "choices": [RAINBOW_BUTTON_DEFAULT, *COLOR_CSS.keys()],
    }


@router.post("/api/appearance-v24")
async def appearance_v24_save(request: Request, db: Session = Depends(get_db)):
    user_id = _current_user_id(request)
    if user_id is None:
        return JSONResponse({"error": "login required"}, status_code=401)
    body = await request.json()
    value = (
        str(body.get("rainbow_buttons", RAINBOW_BUTTON_DEFAULT)).strip().lower()
        if isinstance(body, dict)
        else RAINBOW_BUTTON_DEFAULT
    )
    if value not in RAINBOW_BUTTON_CHOICES:
        return JSONResponse({"error": "invalid rainbow_buttons value"}, status_code=400)
    key = rainbow_button_key(user_id)
    row = db.get(SystemState, key)
    if row:
        row.value = value
    else:
        db.add(SystemState(key=key, value=value))
    db.commit()
    return {"ok": True, "rainbow_buttons": value}


@router.post("/api/appearance-v24/preview")
async def appearance_v24_preview(request: Request, db: Session = Depends(get_db)):
    """Render the current user's form values through the real theme engine.

    This endpoint never persists anything. Personal Appearance can therefore
    preview e-paper, contrast, neutral palette, fonts and radius before Save.
    """
    user_id = _current_user_id(request)
    if user_id is None:
        return JSONResponse({"error": "login required"}, status_code=401)
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)
    theme = _preview_theme(personal_theme(db, user_id), body)
    return Response(
        build_theme_css(theme),
        media_type="text/css",
        headers={"Cache-Control": "no-store"},
    )
