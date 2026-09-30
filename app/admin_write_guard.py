from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.database import SessionLocal
from app.models import User


_ADMIN_WRITE_PATHS = {
    "/api/theme/accessibility",
    "/api/theme/preferences",
}


class AdminWriteGuardMiddleware(BaseHTTPMiddleware):
    """Preserve the existing admin boundary for global appearance mutations."""

    async def dispatch(self, request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path in _ADMIN_WRITE_PATHS:
            db = SessionLocal()
            try:
                user_id = request.session.get("user_id")
                user = db.get(User, int(user_id)) if user_id is not None else None
                allowed = bool(user and user.is_admin)
            except (TypeError, ValueError):
                allowed = False
            finally:
                db.close()
            if not allowed:
                return JSONResponse({"error": "admin required"}, status_code=403)
        return await call_next(request)
