from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.theme import THEME_DEFAULTS, build_theme_css

router = APIRouter()


@router.get("/api/theme/live.css")
def live_theme_css(
    mode: str = Query(THEME_DEFAULTS["mode"]),
    color: str = Query(THEME_DEFAULTS["color"]),
    font: str = Query(THEME_DEFAULTS["font"]),
    base: str = Query(THEME_DEFAULTS["base"]),
    radius: str = Query(THEME_DEFAULTS["radius"]),
    epaper: str = Query(THEME_DEFAULTS["epaper"]),
    contrast: str = Query(THEME_DEFAULTS["contrast"]),
    date_style: str = Query(THEME_DEFAULTS["date_style"]),
):
    values = {
        "mode": mode if mode in {"light", "dark"} else THEME_DEFAULTS["mode"],
        "color": color,
        "font": font,
        "base": base,
        "radius": radius,
        "epaper": "true" if str(epaper).lower() in {"1", "true", "yes", "on"} else "false",
        "contrast": contrast,
        "date_style": date_style,
    }
    return Response(
        build_theme_css(values),
        media_type="text/css",
        headers={"Cache-Control": "no-store"},
    )
