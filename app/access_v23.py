from __future__ import annotations

import json
from copy import deepcopy

from sqlalchemy.orm import Session

from app.models import SystemState, User
from app.theme import COLOR_CSS, CANONICAL_PERSONAL_KEYS, THEME_DEFAULTS, build_theme_css, normalize_theme

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

# Retained only for old clients. v35 has an explicit button_color preference and
# does not use a separate rainbow-button controller anymore.
RAINBOW_BUTTON_DEFAULT = "smooth"
RAINBOW_BUTTON_CHOICES = {RAINBOW_BUTTON_DEFAULT, *COLOR_CSS.keys()}


def _load_json(db: Session, key: str, default):
    row = db.get(SystemState, key)
    if not row or not row.value:
        return deepcopy(default)
    try:
        return json.loads(row.value)
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
    return {key: bool(saved.get(key, default)) for key, default in DEFAULT_USER_PERMISSIONS.items()}


def set_permissions(db: Session, user: User, values: dict) -> dict[str, bool]:
    if user.is_admin:
        return permissions_for_user(db, user)
    cleaned = {key: bool(values.get(key, DEFAULT_USER_PERMISSIONS[key])) for key in DEFAULT_USER_PERMISSIONS}
    _save_json(db, permission_key(user.id), cleaned)
    return cleaned


def has_permission(db: Session, user_id: int | None, permission: str) -> bool:
    if not user_id or permission not in DEFAULT_USER_PERMISSIONS:
        return False
    user = db.get(User, int(user_id))
    return bool(permissions_for_user(db, user).get(permission, False))


def personal_theme(db: Session, user_id: int | None) -> dict[str, str]:
    """Return only this user's appearance, never the legacy global DB theme."""
    if not user_id:
        return normalize_theme(THEME_DEFAULTS)
    saved = _load_json(db, theme_key(int(user_id)), {})
    if not isinstance(saved, dict):
        saved = {}

    # Migrate old single-accent settings without writing during GET. Rainbow used
    # to control both logo and buttons; v35 keeps rainbow on the logo only and
    # uses the previous fixed rainbow-button preference when available.
    if "logo_color" not in saved and "color" in saved:
        saved["logo_color"] = saved["color"]
    if "button_color" not in saved and "color" in saved:
        legacy = str(saved["color"])
        if legacy == "rainbow":
            preference = rainbow_button_preference(db, int(user_id))
            saved["button_color"] = preference if preference in COLOR_CSS else THEME_DEFAULTS["button_color"]
        elif legacy in COLOR_CSS:
            saved["button_color"] = legacy

    return normalize_theme(saved)


def save_personal_theme(db: Session, user_id: int, values: dict) -> dict[str, str]:
    """Persist the canonical personal appearance for exactly one user."""
    current_raw = _load_json(db, theme_key(user_id), {})
    if not isinstance(current_raw, dict):
        current_raw = {}
    merged = dict(personal_theme(db, user_id))
    merged.update(values if isinstance(values, dict) else {})
    normalized = normalize_theme(merged)
    stored = {key: normalized[key] for key in CANONICAL_PERSONAL_KEYS}
    _save_json(db, theme_key(user_id), stored)
    return personal_theme(db, user_id)


def personal_theme_css(db: Session, user_id: int | None) -> str:
    """Render personal CSS plus machine-readable state for the synchronous head bootstrap."""
    theme = personal_theme(db, user_id)
    saved = {
        "mode": theme["mode"],
        "base": theme["base"],
        "button-color": theme["button_color"],
        "logo-color": theme["logo_color"],
        "radius": theme["radius"],
        "font": theme["font"],
        "epaper": theme["epaper"],
        "contrast": theme["contrast"],
    }
    metadata = ":root{" + ";".join(
        f"--b2m-saved-{key}:{value}" for key, value in saved.items()
    ) + "}"
    return metadata + build_theme_css(theme)
