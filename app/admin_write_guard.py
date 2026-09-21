from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


_ADMIN_WRITE_PATHS = {
    "/api/theme/accessibility",
    "/api/theme/preferences",
}


class AdminWriteGuardMiddleware(BaseHTTPMiddleware):
    """Preserve the existing admin boundary for global appearance mutations."""

    async def dispatch(self, request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path in _ADMIN_WRITE_PATHS:
            if not request.session.get("is_admin", False):
                return JSONResponse({"error": "admin required"}, status_code=403)
        return await call_next(request)
