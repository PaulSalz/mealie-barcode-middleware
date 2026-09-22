from __future__ import annotations

import json
from typing import Any

from app.models import SystemState, User
from app.theme import THEME_CHOICES, THEME_DEFAULTS, build_theme_css, get_theme as get_global_theme

FONT_SIZE_DEFAULT = 100
_RAINBOW_COLORS = ("#e03131", "#f08c00", "#f2c037", "#2fb344", "#17a2b8", "#4263eb", "#ae3ec9", "#d6336c")


def _global_font_size(db) -> int:
    row = db.get(SystemState, "ui.font_size_percent")
    try:
        value = int(float(row.value)) if row and row.value else FONT_SIZE_DEFAULT
    except (TypeError, ValueError):
        value = FONT_SIZE_DEFAULT
    return max(80, min(120, value))


def _decode_user_appearance(user: User | None) -> dict[str, Any]:
    if not user:
        return {}
    try:
        data = json.loads(getattr(user, "appearance_json", None) or "{}")
    except (TypeError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def get_user_appearance(db, user_id: int | None) -> dict[str, Any]:
    """Return one user's appearance, inheriting the old global theme until saved.

    Existing installations therefore keep their current look after migration. As
    soon as a user saves Appearance, a complete personal snapshot is stored and
    later changes by another user no longer affect it.
    """
    inherited: dict[str, Any] = dict(get_global_theme(db))
    inherited["font_size"] = _global_font_size(db)
    if not user_id:
        return inherited
    user = db.get(User, int(user_id))
    saved = _decode_user_appearance(user)
    result = dict(inherited)
    result.update(saved)
    return result


def _validated(current: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    result = dict(current)
    for key in THEME_DEFAULTS:
        if key not in values:
            continue
        value = str(values[key]).strip()
        if key == "color" and value == "rainbow":
            result[key] = value
            continue
        if key in THEME_CHOICES and value not in THEME_CHOICES[key]:
            continue
        if key == "contrast":
            try:
                value = str(max(0, min(100, int(float(value)))))
            except (TypeError, ValueError):
                value = THEME_DEFAULTS["contrast"]
        if key == "epaper":
            value = "true" if value.lower() in {"1", "true", "yes", "on"} else "false"
        result[key] = value
    if "font_size" in values:
        try:
            result["font_size"] = max(80, min(120, int(float(values["font_size"]))))
        except (TypeError, ValueError):
            pass
    return result


def save_user_appearance(db, user_id: int, values: dict[str, Any]) -> dict[str, Any]:
    user = db.get(User, int(user_id))
    if not user:
        raise ValueError("User not found")
    current = get_user_appearance(db, user.id)
    updated = _validated(current, values)
    user.appearance_json = json.dumps(updated, ensure_ascii=False, separators=(",", ":"))
    db.commit()
    return updated


def theme_for_request(request) -> dict[str, Any]:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        return get_user_appearance(db, request.session.get("user_id"))
    finally:
        db.close()


def _rainbow_css() -> str:
    c = _RAINBOW_COLORS
    return f"""
@keyframes b2m-rainbow-vars {{
  0%,100% {{--tblr-primary:{c[0]};--tblr-primary-rgb:224,49,49}}
  14% {{--tblr-primary:{c[1]};--tblr-primary-rgb:240,140,0}}
  28% {{--tblr-primary:{c[2]};--tblr-primary-rgb:242,192,55}}
  42% {{--tblr-primary:{c[3]};--tblr-primary-rgb:47,179,68}}
  56% {{--tblr-primary:{c[4]};--tblr-primary-rgb:23,162,184}}
  70% {{--tblr-primary:{c[5]};--tblr-primary-rgb:66,99,235}}
  84% {{--tblr-primary:{c[6]};--tblr-primary-rgb:174,62,201}}
  94% {{--tblr-primary:{c[7]};--tblr-primary-rgb:214,51,108}}
}}
html{{animation:b2m-rainbow-vars 18s linear infinite}}
@keyframes b2m-rainbow-brand-flow {{0%{{background-position:0% 50%}}100%{{background-position:300% 50%}}}}
.b2m-dashboard-brand{{
  background:linear-gradient(90deg,{','.join(c)},{c[0]});
  background-size:300% 100%;
  -webkit-background-clip:text;background-clip:text;color:transparent!important;
  animation:b2m-rainbow-brand-flow 14s linear infinite;
}}
.b2m-dashboard-brand i{{color:inherit!important}}
"""


def build_user_theme_css(theme: dict[str, Any]) -> str:
    css = build_theme_css({key: str(theme.get(key, default)) for key, default in THEME_DEFAULTS.items()})
    if str(theme.get("color")) == "rainbow" and str(theme.get("epaper", "false")) != "true":
        css += _rainbow_css()
    return css
