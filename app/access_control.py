from __future__ import annotations

import json
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

from app.database import SessionLocal
from app.models import User


PERMISSION_DEFS: dict[str, dict[str, Any]] = {
    "printer_settings": {
        "label": "Printer settings",
        "description": "Configure B21 connection, roll profiles, calibration and printer runtime settings.",
        "default": True,
        "icon": "ti-printer",
    },
    "pause_control": {
        "label": "Scan & Link control",
        "description": "Start and stop Scan & Link mode from the navigation and API.",
        "default": False,
        "icon": "ti-link-plus",
    },
    "database_admin": {
        "label": "Database administration",
        "description": "View storage details, download backups and purge/reset application data.",
        "default": False,
        "icon": "ti-database",
    },
}


def _decode_permissions(value: str | None) -> dict[str, bool]:
    try:
        data = json.loads(value or "{}")
    except (TypeError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {key: bool(data.get(key, meta["default"])) for key, meta in PERMISSION_DEFS.items()}


def permission_map(user: User | None) -> dict[str, bool]:
    if not user:
        return {key: False for key in PERMISSION_DEFS}
    if user.is_admin:
        return {key: True for key in PERMISSION_DEFS}
    return _decode_permissions(getattr(user, "permissions_json", None))


def permission_ids(user: User | None) -> list[str]:
    return [key for key, enabled in permission_map(user).items() if enabled]


def save_permissions(user: User, values: dict[str, Any]) -> dict[str, bool]:
    clean = {key: bool(values.get(key, meta["default"])) for key, meta in PERMISSION_DEFS.items()}
    user.permissions_json = json.dumps(clean, ensure_ascii=False, separators=(",", ":"))
    return clean


def has_permission(request: Request, permission: str) -> bool:
    if request.session.get("is_admin", False):
        return True
    return permission in set(request.session.get("permissions") or [])


def require_permission_response(request: Request, permission: str):
    if has_permission(request, permission):
        return None
    if request.url.path.startswith("/api/") or request.headers.get("accept", "").startswith("application/json"):
        return JSONResponse({"error": f"permission required: {permission}"}, status_code=403)
    return RedirectResponse("/settings?tab=appearance&forbidden=1", status_code=303)


class CapabilitySessionMiddleware(BaseHTTPMiddleware):
    """Keep signed-session capabilities synchronized with the current User row."""

    async def dispatch(self, request: Request, call_next):
        # Static files neither render user data nor authorize mutations. Avoid a
        # database lookup for every JS/CSS/icon request during page load.
        if request.url.path.startswith("/static/"):
            return await call_next(request)

        user_id = request.session.get("user_id")
        if user_id:
            db = SessionLocal()
            try:
                user = db.get(User, user_id)
                if user:
                    effective = permission_ids(user)
                    if request.session.get("permissions") != effective:
                        request.session["permissions"] = effective
                    # Date formatting is rendered server-side in Jinja. Cache only
                    # this harmless appearance preference in the signed session so
                    # each timestamp does not need another database query.
                    try:
                        from app.user_theme import get_user_appearance

                        appearance = get_user_appearance(db, user.id)
                        date_style = appearance.get("date_style", "medium")
                        if request.session.get("theme_date_style") != date_style:
                            request.session["theme_date_style"] = date_style
                    except Exception:
                        pass
            finally:
                db.close()
        return await call_next(request)


class CapabilityGuardMiddleware(BaseHTTPMiddleware):
    """Enforce capability boundaries independently of navigation visibility."""

    async def dispatch(self, request: Request, call_next):
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return await call_next(request)

        path = request.url.path
        required: str | None = None

        if path.startswith("/settings/admin/") or path == "/api/settings/storage":
            required = "database_admin"
        elif path in {"/api/settings/pause", "/api/settings/resume"}:
            required = "pause_control"
        elif path == "/api/settings/niim":
            required = "printer_settings"
        elif path in {"/labels/b21/connect", "/labels/b21/disconnect", "/labels/b21/rfid-bind"}:
            required = "printer_settings"
        elif path == "/labels/b21/calibration" or path == "/labels/b21/profiles" or path.startswith("/labels/b21/profiles/"):
            required = "printer_settings"

        if required and not has_permission(request, required):
            return require_permission_response(request, required)
        return await call_next(request)
