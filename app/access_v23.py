from __future__ import annotations

import json
from copy import deepcopy

from sqlalchemy.orm import Session

from app.models import SystemState, User
from app.theme import COLOR_CSS, THEME_DEFAULTS, build_theme_css, get_theme

PERMISSION_CATALOG = [
    {"id": "printer", "label": "Printer & labels", "description": "Connect/configure the B21, edit roll settings and submit print jobs."},
    {"id": "actions", "label": "Actions", "description": "Create, edit, test and delete barcode Actions."},
    {"id": "items", "label": "Items", "description": "Create, edit, sync and change item mappings/settings."},
    {"id": "scanning", "label": "Scanning controls", "description": "Use Scan & Link pause/resume controls."},
    {"id": "configuration", "label": "System configuration", "description": "Change integration, lookup, matching and system settings."},
    {"id": "tokens", "label": "Scanner tokens", "description": "Create and revoke scanner API tokens."},
    {"id": "users", "label": "User management", "description": "Manage accounts and granular permissions."},
    {"id": "database", "label": "Database administration", "description": "Back up, purge or reset application data."},
]

DEFAULT_USER_PERMISSIONS = {
    "printer": True,
    "actions": True,
    "items": True,
    "scanning": False,
    "configuration": False,
    "tokens": False,
    "users": False,
    "database": False,
}

RAINBOW_BUTTON_DEFAULT = "smooth"
RAINBOW_BUTTON_CHOICES = {RAINBOW_BUTTON_DEFAULT, *COLOR_CSS.keys()}


def _load_json(db: Session, key: str, default):
    row = db.get(SystemState, key)
    if not row or not row.value:
        return deepcopy(default)
    try:
        value = json.loads(row.value)
        return value
    except (TypeError, ValueError):
        return deepcopy(default)


def _save_json(db: Session, key: str, value) -> None:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    row = db.get(SystemState, key)
    if row:
        row.value = encoded
    else:
        db.add(SystemState(key=key, value=encoded))
    db.commit()


def permission_key(user_id: int) -> str:
    return f"access.user.{int(user_id)}"


def theme_key(user_id: int) -> str:
    return f"appearance.user.{int(user_id)}"


def rainbow_button_key(user_id: int) -> str:
    return f"appearance.v24.user.{int(user_id)}.rainbow_buttons"


def rainbow_button_preference(db: Session, user_id: int | None) -> str:
    if not user_id:
        return RAINBOW_BUTTON_DEFAULT
    row = db.get(SystemState, rainbow_button_key(int(user_id)))
    value = str(row.value).strip().lower() if row and row.value else RAINBOW_BUTTON_DEFAULT
    return value if value in RAINBOW_BUTTON_CHOICES else RAINBOW_BUTTON_DEFAULT


def permissions_for_user(db: Session, user: User | None) -> dict[str, bool]:
    if not user:
        return {key: False for key in DEFAULT_USER_PERMISSIONS}
    if user.is_admin:
        return {key: True for key in DEFAULT_USER_PERMISSIONS}
    saved = _load_json(db, permission_key(user.id), {})
    if not isinstance(saved, dict):
        saved = {}
    return {
        key: bool(saved.get(key, default))
        for key, default in DEFAULT_USER_PERMISSIONS.items()
    }


def set_permissions(db: Session, user: User, values: dict) -> dict[str, bool]:
    if user.is_admin:
        return permissions_for_user(db, user)
    cleaned = {
        key: bool(values.get(key, DEFAULT_USER_PERMISSIONS[key]))
        for key in DEFAULT_USER_PERMISSIONS
    }
    _save_json(db, permission_key(user.id), cleaned)
    return cleaned


def has_permission(db: Session, user_id: int | None, permission: str) -> bool:
    if not user_id or permission not in DEFAULT_USER_PERMISSIONS:
        return False
    user = db.get(User, int(user_id))
    return bool(permissions_for_user(db, user).get(permission, False))


def personal_theme(db: Session, user_id: int | None) -> dict[str, str]:
    base = get_theme(db)
    if not user_id:
        return base
    saved = _load_json(db, theme_key(int(user_id)), {})
    if not isinstance(saved, dict):
        return base
    result = dict(base)
    for key in THEME_DEFAULTS:
        if key in saved:
            result[key] = str(saved[key])
    return result


def save_personal_theme(db: Session, user_id: int, values: dict) -> dict[str, str]:
    current = _load_json(db, theme_key(user_id), {})
    if not isinstance(current, dict):
        current = {}
    for key in THEME_DEFAULTS:
        if key in values:
            current[key] = str(values[key])
    _save_json(db, theme_key(user_id), current)
    return personal_theme(db, user_id)


def personal_theme_css(db: Session, user_id: int | None) -> str:
    theme = personal_theme(db, user_id)
    css = build_theme_css(theme)

    # This stylesheet is loaded as render-blocking CSS in base.html. Include the
    # per-user Rainbow button preference here so the first painted frame already
    # has the final accent instead of waiting for ui-v24.js + /api/appearance-v24.
    if theme.get("color") == "rainbow":
        if theme.get("epaper") == "true":
            css += (
                ":root{animation:none!important}"
                ".b2m-brand-text{animation:none!important;background:none!important;"
                "color:#000!important;-webkit-text-fill-color:#000!important}"
                ".btn-primary{animation:none!important}"
            )
        else:
            preference = rainbow_button_preference(db, user_id)
            if preference != RAINBOW_BUTTON_DEFAULT and preference in COLOR_CSS:
                color = COLOR_CSS[preference]
                css += (
                    f":root{{animation:none!important;--tblr-primary:{color['hex']}!important;"
                    f"--tblr-primary-rgb:{color['rgb']}!important}}"
                    ".btn-primary{animation:none!important}"
                )
    return css
