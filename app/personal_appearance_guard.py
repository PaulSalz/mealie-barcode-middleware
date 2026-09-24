from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse


class PersonalAppearanceOnlyMiddleware(BaseHTTPMiddleware):
    """Retire the old global Appearance settings entry points.

    Appearance is always a per-user concern. Existing bookmarks to the former
    admin tab are redirected to the current user's profile page and the old
    global form endpoint can no longer mutate a process-wide theme.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path == "/settings/theme":
            return RedirectResponse("/profile/appearance", status_code=303)
        if path == "/settings" and request.query_params.get("tab") == "appearance":
            return RedirectResponse("/profile/appearance", status_code=303)
        return await call_next(request)
