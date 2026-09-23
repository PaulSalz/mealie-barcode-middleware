import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.templating import Jinja2Templates
from jinja2 import pass_context

from app.config import settings
from app.i18n import template_language, template_translate
from app.theme import THEME_DEFAULTS, build_theme_css

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

_tz = ZoneInfo(settings.timezone)
_GERMAN_MONTHS = (
    "", "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)

_static_dir = BASE_DIR / "static"
_mtimes = "".join(str(f.stat().st_mtime_ns) for f in sorted(_static_dir.rglob("*.js")) if f.is_file())
_mtimes += "".join(str(f.stat().st_mtime_ns) for f in sorted(_static_dir.rglob("*.css")) if f.is_file())
ASSET_VERSION = hashlib.md5(_mtimes.encode()).hexdigest()[:8]

_current_theme: dict[str, str] = dict(THEME_DEFAULTS)
_current_theme_css: str = ""


def get_cached_theme() -> dict[str, str]:
    return _current_theme


def get_cached_theme_css() -> str:
    return _current_theme_css


def set_cached_theme(theme: dict[str, str]) -> None:
    global _current_theme_css
    _current_theme.update(theme)
    _current_theme_css = build_theme_css(theme)


def _effective_theme_for_request(request) -> dict[str, str]:
    """Return the effective theme for the request without a client-side round trip.

    The cached theme is the administrator-controlled default. Signed-in users may
    override any of those values, so using the cached default in base.html caused
    every navigation to start in the wrong mode/background until JavaScript fixed
    it after first paint.
    """
    if request is None:
        return dict(_current_theme)
    try:
        user_id = request.session.get("user_id")
    except Exception:
        user_id = None
    if not user_id:
        return dict(_current_theme)

    # Lazy imports avoid a templating <-> router/access import cycle at startup.
    from app.access_v23 import personal_theme
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        return personal_theme(db, int(user_id))
    except (TypeError, ValueError):
        return dict(_current_theme)
    finally:
        db.close()


@pass_context
def _template_theme(context) -> dict[str, str]:
    return _effective_theme_for_request(context.get("request"))


def _as_utc(value: datetime | None) -> datetime | None:
    if not value:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _localtime(value, fmt=None):
    value = _as_utc(value)
    if not value:
        return "—"
    local = value.astimezone(_tz)
    if fmt:
        return local.strftime(fmt)
    style = _current_theme.get("date_style", THEME_DEFAULTS["date_style"])
    if style == "short":
        return local.strftime("%d.%m.%y %H:%M")
    if style == "long":
        return f"{local.day}. {_GERMAN_MONTHS[local.month]} {local.year}, {local:%H:%M}"
    return local.strftime("%d.%m.%Y %H:%M")


def _relative_time(value):
    value = _as_utc(value)
    if not value:
        return "Never"
    seconds = max(0, int((datetime.now(timezone.utc) - value).total_seconds()))
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hr{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days < 7:
        return f"{days} day{'s' if days != 1 else ''} ago"
    weeks = days // 7
    if days < 35:
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    months = max(1, days // 30)
    if days < 365:
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = max(1, days // 365)
    return f"{years} year{'s' if years != 1 else ''} ago"


def _fromjson(value):
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return []


templates.env.filters["localtime"] = _localtime
templates.env.filters["relative_time"] = _relative_time
templates.env.filters["fromjson"] = _fromjson
templates.env.globals["v"] = ASSET_VERSION
# Keep the historical get_theme() template API, but make it request-aware so
# base.html starts in the authenticated user's final mode before first paint.
templates.env.globals["get_theme"] = _template_theme
templates.env.globals["t"] = template_translate
templates.env.globals["tr"] = template_translate
templates.env.globals["ui_language"] = template_language
