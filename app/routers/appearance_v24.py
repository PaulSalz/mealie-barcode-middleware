from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.access_v23 import personal_theme, save_personal_theme
from app.database import get_db
from app.models import SystemState
from app.theme import THEME_CHOICES, THEME_DEFAULTS, build_theme_css, normalize_theme

router = APIRouter()


def _current_user_id(request: Request) -> int | None:
    value = request.session.get("user_id")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _advanced_settings_key(user_id: int) -> str:
    return f"appearance.v29.user.{int(user_id)}.advanced_settings"


def _advanced_settings_preference(db: Session, user_id: int | None) -> bool:
    if not user_id:
        return False
    row = db.get(SystemState, _advanced_settings_key(int(user_id)))
    if not row or not row.value:
        return False
    return str(row.value).strip().lower() in {"1", "true", "yes", "on"}


def _theme_from_form(form) -> dict[str, str]:
    return {
        "mode": str(form.get("theme_mode", THEME_DEFAULTS["mode"])),
        "logo_color": str(form.get("theme_logo_color", THEME_DEFAULTS["logo_color"])),
        "button_color": str(form.get("theme_button_color", THEME_DEFAULTS["button_color"])),
        "font": str(form.get("theme_font", THEME_DEFAULTS["font"])),
        "base": str(form.get("theme_base", THEME_DEFAULTS["base"])),
        "radius": str(form.get("theme_radius", THEME_DEFAULTS["radius"])),
        "date_style": str(form.get("theme_date_style", THEME_DEFAULTS["date_style"])),
        "epaper": "true" if form.get("theme_epaper") else "false",
        "contrast": str(form.get("theme_contrast", THEME_DEFAULTS["contrast"])),
    }


@router.get("/api/appearance-v24")
def appearance_v24_get(request: Request, db: Session = Depends(get_db)):
    """Compatibility URL for the canonical per-user appearance API."""
    user_id = _current_user_id(request)
    if user_id is None:
        return JSONResponse({"error": "login required"}, status_code=401)
    theme = personal_theme(db, user_id)
    return {
        "theme": theme,
        "advanced_settings": _advanced_settings_preference(db, user_id),
        # Legacy clients expect this field; rainbow buttons no longer exist in
        # v35 because button_color is explicit and never supports rainbow.
        "rainbow_buttons": theme.get("button_color", "blue"),
        "choices": {
            "mode": THEME_CHOICES["mode"],
            "logo_color": THEME_CHOICES["logo_color"],
            "button_color": THEME_CHOICES["button_color"],
            "font": THEME_CHOICES["font"],
            "base": THEME_CHOICES["base"],
            "radius": THEME_CHOICES["radius"],
            "date_style": THEME_CHOICES["date_style"],
        },
    }


@router.post("/api/appearance-v24/mode")
async def appearance_v24_mode(request: Request, db: Session = Depends(get_db)):
    """Persist the navbar light/dark switch immediately for the current user."""
    user_id = _current_user_id(request)
    if user_id is None:
        return JSONResponse({"error": "login required"}, status_code=401)
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)
    mode = str(body.get("mode", "")).strip().lower()
    if mode not in THEME_CHOICES["mode"]:
        return JSONResponse({"error": "invalid mode"}, status_code=400)
    theme = save_personal_theme(db, user_id, {"mode": mode})
    return {"ok": True, "mode": mode, "theme": theme}


@router.post("/api/appearance-v24")
async def appearance_v24_save(request: Request, db: Session = Depends(get_db)):
    """Persist personal appearance. Live preview is entirely browser-local."""
    user_id = _current_user_id(request)
    if user_id is None:
        return JSONResponse({"error": "login required"}, status_code=401)
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)

    if "advanced_settings" in body:
        raw = body.get("advanced_settings")
        enabled = raw if isinstance(raw, bool) else str(raw).strip().lower() in {"1", "true", "yes", "on"}
        key = _advanced_settings_key(user_id)
        row = db.get(SystemState, key)
        encoded = "true" if enabled else "false"
        if row:
            row.value = encoded
        else:
            db.add(SystemState(key=key, value=encoded))
        db.commit()

    payload = body.get("theme") if isinstance(body.get("theme"), dict) else body
    theme_fields = {
        key: value for key, value in payload.items()
        if key in {"mode", "logo_color", "button_color", "font", "base", "radius", "epaper", "contrast", "date_style", "color"}
    }
    theme = save_personal_theme(db, user_id, theme_fields) if theme_fields else personal_theme(db, user_id)
    return {"ok": True, "theme": theme, "advanced_settings": _advanced_settings_preference(db, user_id)}


@router.post("/profile/appearance")
async def profile_appearance_save_v35(request: Request, db: Session = Depends(get_db)):
    """Progressive-enhancement fallback; JS normally saves through the JSON API."""
    user_id = _current_user_id(request)
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    save_personal_theme(db, user_id, _theme_from_form(form))
    return RedirectResponse("/profile/appearance?saved=1", status_code=303)


@router.post("/api/appearance-v24/preview")
async def appearance_v24_preview(request: Request, db: Session = Depends(get_db)):
    """Compatibility preview endpoint; v35 no longer depends on it for UX."""
    user_id = _current_user_id(request)
    if user_id is None:
        return JSONResponse({"error": "login required"}, status_code=401)
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)
    merged = dict(personal_theme(db, user_id))
    merged.update(body)
    return Response(build_theme_css(normalize_theme(merged)), media_type="text/css", headers={"Cache-Control": "no-store"})
