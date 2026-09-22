from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class AdminWriteGuardMiddleware(BaseHTTPMiddleware):
    """Compatibility middleware kept for older deployments.

    Appearance writes are user-scoped as of v2026.09.22.2, so they must no
    longer be blocked for non-admin users here. Capability-sensitive mutations
    are enforced by CapabilityGuardMiddleware and by their route handlers.
    """

    async def dispatch(self, request: Request, call_next):
        return await call_next(request)
