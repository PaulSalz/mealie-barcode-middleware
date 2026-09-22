from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

from app.access_v23 import has_permission
from app.database import SessionLocal

_SAFE = {"GET", "HEAD", "OPTIONS"}

# Prefixes are intentionally narrow. Scanner-token authenticated routes are not
# part of this guard; it protects session-authenticated UI mutations only.
_RULES = [
    ("/labels/b21/", "printer"),
    ("/actions", "actions"),
    ("/api/actions/", "actions"),
    ("/items", "items"),
    ("/api/items/", "items"),
]


class PermissionGuardV23Middleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in _SAFE:
            return await call_next(request)

        path = request.url.path
        permission = next((perm for prefix, perm in _RULES if path.startswith(prefix)), None)
        if permission is None:
            return await call_next(request)

        # LoginRequiredMiddleware already validates the session on normal UI
        # routes. Admins retain the existing all-access behaviour.
        if request.session.get("is_admin", False):
            return await call_next(request)

        user_id = request.session.get("user_id")
        db = SessionLocal()
        try:
            allowed = has_permission(db, user_id, permission)
        finally:
            db.close()
        if allowed:
            return await call_next(request)

        if path.startswith("/api/") or request.headers.get("accept", "").startswith("application/json"):
            return JSONResponse({"error": "permission required", "permission": permission}, status_code=403)
        return RedirectResponse(f"/?permission_denied={permission}", status_code=303)
