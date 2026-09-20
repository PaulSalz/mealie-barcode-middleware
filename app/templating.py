import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.templating import Jinja2Templates

from app.config import settings
from app.theme import THEME_DEFAULTS, build_theme_css

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

_tz = ZoneInfo(settings.timezone)

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

# Global theme cache — loaded once at startup, updated on save
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


def _localtime(value, fmt="%Y-%m-%d %H:%M"):
    """Jinja2 filter: convert a UTC datetime to the configured local timezone."""
    value = _as_utc(value)
    if not value:
        return "—"
    return value.astimezone(_tz).strftime(fmt)


def _relative_time(value):
    """Compact human-readable age for recent timestamps; absolute local date for older values."""
    value = _as_utc(value)
    if not value:
        return "Never"
    seconds = max(0, int((datetime.now(timezone.utc) - value).total_seconds()))
    if seconds < 10:
        return "just now"
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h ago"
    days = hours // 24
    if days < 14:
        return f"{days}d ago"
    return value.astimezone(_tz).strftime("%Y-%m-%d")


def _fromjson(value):
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return []


templates.env.filters["localtime"] = _localtime
templates.env.filters["relative_time"] = _relative_time
templates.env.filters["fromjson"] = _fromjson
templates.env.globals["v"] = ASSET_VERSION
templates.env.globals["get_theme"] = get_cached_theme
