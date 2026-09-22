import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import pass_context
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.theme import THEME_DEFAULTS, build_theme_css

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

_tz = ZoneInfo(settings.timezone)
_GERMAN_MONTHS = (
    "", "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)

# Cache-buster: short hash of JS/CSS modification times (recomputed on startup)
_static_dir = BASE_DIR / "static"
_mtimes = "".join(
    str(f.stat().st_mtime_ns)
    for f in sorted(_static_dir.rglob("*.js"))
    if f.is_file()
)
_mtimes += "".join(
    str(f.stat().st_mtime_ns)
    for f in sorted(_static_dir.rglob("*.css"))
    if f.is_file()
)
ASSET_VERSION = hashlib.md5(_mtimes.encode()).hexdigest()[:8]

# Legacy/global theme cache remains as the inheritance source for users that
# have not saved personal Appearance settings yet.
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


def _as_utc(value: datetime | None) -> datetime | None:
    if not value:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_localtime(value, fmt=None, style: str | None = None):
    value = _as_utc(value)
    if not value:
        return "—"
    local = value.astimezone(_tz)
    if fmt:
        return local.strftime(fmt)
    style = style or _current_theme.get("date_style", THEME_DEFAULTS["date_style"])
    if style == "short":
        return local.strftime("%d.%m.%y %H:%M")
    if style == "long":
        return f"{local.day}. {_GERMAN_MONTHS[local.month]} {local.year}, {local:%H:%M}"
    return local.strftime("%d.%m.%Y %H:%M")


def _localtime(value, fmt=None):
    """Python-side formatter used by routers and helpers."""
    return _format_localtime(value, fmt)


@pass_context
def _localtime_filter(context, value, fmt=None):
    """Jinja formatter using the signed session's per-user date preference."""
    request = context.get("request")
    style = None
    if request is not None:
        style = request.session.get("theme_date_style")
    return _format_localtime(value, fmt, style)


def _relative_time(value):
    """Compact human-readable age used consistently throughout the UI."""
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


def _get_user_theme(request):
    from app.user_theme import theme_for_request

    return theme_for_request(request)


templates.env.filters["localtime"] = _localtime_filter
templates.env.filters["relative_time"] = _relative_time
templates.env.filters["fromjson"] = _fromjson
templates.env.globals["v"] = ASSET_VERSION
templates.env.globals["get_theme"] = get_cached_theme
templates.env.globals["get_user_theme"] = _get_user_theme
