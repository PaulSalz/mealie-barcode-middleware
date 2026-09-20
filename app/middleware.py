"""Security middleware — headers, CSRF origin check, and session auth."""

import json
import logging
import secrets
from base64 import b64decode, b64encode
from urllib.parse import quote, urlparse

from itsdangerous.exc import BadSignature
from starlette.datastructures import MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import Session, SessionMiddleware
from starlette.requests import HTTPConnection, Request
from starlette.responses import RedirectResponse, Response
from starlette.types import Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_CSRF_EXEMPT_PREFIXES = ("/scan", "/scan/app", "/scanner/heartbeat")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "connect-src 'self'; "
            "font-src 'self'; "
            "img-src 'self' data:; "
            "worker-src 'self'"
        )
        return response


class CSRFOriginMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in _SAFE_METHODS:
            return await call_next(request)

        path = request.url.path
        for prefix in _CSRF_EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        expected_host = request.headers.get("host", "")
        origin = request.headers.get("origin")
        if origin:
            parsed = urlparse(origin)
            if parsed.netloc == expected_host:
                return await call_next(request)
            logger.warning(f"CSRF blocked: origin '{origin}' != host '{expected_host}' on {path}")
            return Response("Forbidden — origin mismatch", status_code=403)

        referer = request.headers.get("referer")
        if referer:
            parsed = urlparse(referer)
            if parsed.netloc == expected_host:
                return await call_next(request)
            logger.warning(f"CSRF blocked: referer '{referer}' != host '{expected_host}' on {path}")
            return Response("Forbidden — referer mismatch", status_code=403)

        logger.warning(f"CSRF blocked: no origin/referer on {request.method} {path}")
        return Response("Forbidden — missing origin", status_code=403)


class RememberMeSessionMiddleware(SessionMiddleware):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        connection = HTTPConnection(scope)
        initial_session_was_empty = True

        if self.session_cookie in connection.cookies:
            data = connection.cookies[self.session_cookie].encode("utf-8")
            try:
                data = self.signer.unsign(data, max_age=self.max_age)
                scope["session"] = Session(json.loads(b64decode(data)))
                initial_session_was_empty = False
            except BadSignature:
                scope["session"] = Session()
        else:
            scope["session"] = Session()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                session: Session = scope["session"]
                headers = MutableHeaders(scope=message)
                if session.accessed:
                    headers.add_vary_header("Cookie")
                if session.modified and session:
                    data = b64encode(json.dumps(dict(session)).encode("utf-8"))
                    data = self.signer.sign(data)
                    cookie_max_age = self.max_age if session.get("_remember") else None
                    header_value = (
                        "{session_cookie}={data}; path={path}; "
                        "{max_age}{security_flags}"
                    ).format(
                        session_cookie=self.session_cookie,
                        data=data.decode("utf-8"),
                        path=self.path,
                        max_age=f"Max-Age={cookie_max_age}; " if cookie_max_age else "",
                        security_flags=self.security_flags,
                    )
                    headers.append("Set-Cookie", header_value)
                elif session.modified and not initial_session_was_empty:
                    header_value = (
                        "{session_cookie}={data}; path={path}; "
                        "{expires}{security_flags}"
                    ).format(
                        session_cookie=self.session_cookie,
                        data="null",
                        path=self.path,
                        expires="expires=Thu, 01 Jan 1970 00:00:00 GMT; ",
                        security_flags=self.security_flags,
                    )
                    headers.append("Set-Cookie", header_value)
            await send(message)

        await self.app(scope, receive, send_wrapper)


_AUTH_EXEMPT_PREFIXES = (
    "/login",
    "/setup",
    "/static",
    "/scan",
    "/scanner/heartbeat",
    "/health",
    "/api/docs",
    "/api/redoc",
    "/openapi.json",
    "/theme.css",
    "/favicon",
)


def _generate_secret_key() -> str:
    from app.config import settings
    key_file = settings.db_path.rsplit("/", 1)[0] + "/.session_secret"
    try:
        with open(key_file) as f:
            key = f.read().strip()
            if key:
                return key
    except FileNotFoundError:
        pass
    key = secrets.token_hex(32)
    try:
        with open(key_file, "w") as f:
            f.write(key)
    except OSError:
        pass
    return key


def get_session_secret() -> str:
    if not hasattr(get_session_secret, "_key"):
        get_session_secret._key = _generate_secret_key()
    return get_session_secret._key


class LoginRequiredMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        for prefix in _AUTH_EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        from app.database import SessionLocal
        from app.models import User

        user_id = request.session.get("user_id")
        if user_id:
            db = SessionLocal()
            try:
                user = db.get(User, user_id)
            finally:
                db.close()

            if user:
                if request.session.get("is_admin") != user.is_admin:
                    request.session["is_admin"] = user.is_admin
                return await call_next(request)
            request.session.clear()

        db = SessionLocal()
        try:
            has_users = db.query(User.id).first() is not None
        finally:
            db.close()

        if not has_users:
            return RedirectResponse("/setup", status_code=303)

        next_url = quote(str(request.url.path), safe="/:@!$&'()*+,;=-._~")
        qs = str(request.url.query)
        if qs:
            next_url += "?" + qs
        return RedirectResponse(f"/login?next={quote(next_url, safe='')}", status_code=303)
