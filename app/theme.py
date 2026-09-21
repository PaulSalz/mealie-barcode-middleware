"""Theme settings — global appearance stored in the DB."""

import logging

from app.models import SettingsOverride
from app.utils import utcnow

logger = logging.getLogger(__name__)
_PREFIX = "theme_"

THEME_DEFAULTS = {
    "mode": "light",
    "color": "blue",
    "font": "sans-serif",
    "base": "gray",
    "radius": "1",
    "epaper": "false",
    "contrast": "65",
    "date_style": "medium",
}

THEME_CHOICES = {
    "mode": ["light", "dark"],
    "color": ["blue", "azure", "indigo", "purple", "pink", "red", "orange", "yellow", "lime", "green", "teal", "cyan"],
    "font": ["sans-serif", "serif", "monospace", "comic", "dyslexia"],
    "base": ["slate", "gray", "zinc", "neutral", "stone"],
    "radius": ["0", "0.5", "1", "1.5", "2"],
    "epaper": ["false", "true"],
    "date_style": ["short", "medium", "long"],
}

COLOR_CSS = {
    "blue":{"hex":"#066fd1","rgb":"6,111,209"}, "azure":{"hex":"#4299e1","rgb":"66,153,225"},
    "indigo":{"hex":"#4263eb","rgb":"66,99,235"}, "purple":{"hex":"#ae3ec9","rgb":"174,62,201"},
    "pink":{"hex":"#d6336c","rgb":"214,51,108"}, "red":{"hex":"#d63939","rgb":"214,57,57"},
    "orange":{"hex":"#f76707","rgb":"247,103,7"}, "yellow":{"hex":"#f59f00","rgb":"245,159,0"},
    "lime":{"hex":"#74b816","rgb":"116,184,22"}, "green":{"hex":"#2fb344","rgb":"47,179,68"},
    "teal":{"hex":"#0ca678","rgb":"12,166,120"}, "cyan":{"hex":"#17a2b8","rgb":"23,162,184"},
}

FONT_CSS = {
    "sans-serif": '"Inter Var",Inter,-apple-system,BlinkMacSystemFont,San Francisco,Segoe UI,Roboto,Helvetica Neue,sans-serif',
    "serif": "Georgia,Times New Roman,times,serif",
    "monospace": "Monaco,Consolas,Liberation Mono,Courier New,monospace",
    "comic": "Comic Sans MS,Comic Sans,Chalkboard SE,Comic Neue,sans-serif,cursive",
    "dyslexia": 'OpenDyslexic,"Atkinson Hyperlegible",Verdana,Tahoma,Arial,sans-serif',
}

GRAY_CSS = {
    "gray": None,
    "slate":{"50":"#f8fafc","100":"#f1f5f9","200":"#e2e8f0","300":"#cbd5e1","400":"#94a3b8","500":"#64748b","600":"#475569","700":"#334155","800":"#1e293b","900":"#0f172a","950":"#020617"},
    "zinc":{"50":"#fafafa","100":"#f4f4f5","200":"#e4e4e7","300":"#d4d4d8","400":"#a1a1aa","500":"#71717a","600":"#52525b","700":"#3f3f46","800":"#27272a","900":"#18181b","950":"#09090b"},
    "neutral":{"50":"#fafafa","100":"#f5f5f5","200":"#e5e5e5","300":"#d4d4d4","400":"#a3a3a3","500":"#737373","600":"#525252","700":"#404040","800":"#262626","900":"#171717","950":"#0a0a0a"},
    "stone":{"50":"#fafaf9","100":"#f5f5f4","200":"#e7e5e4","300":"#d6d3d1","400":"#a8a29e","500":"#78716c","600":"#57534e","700":"#44403c","800":"#292524","900":"#1c1917","950":"#0c0a09"},
}


def get_theme(db) -> dict[str, str]:
    rows = db.query(SettingsOverride).filter(SettingsOverride.key.startswith(_PREFIX)).all()
    overrides = {row.key[len(_PREFIX):]: row.value for row in rows}
    return {key: overrides.get(key, default) for key, default in THEME_DEFAULTS.items()}


def save_theme(db, values: dict[str, str]) -> list[str]:
    """Persist only keys explicitly supplied by the caller."""
    changed: list[str] = []
    current = get_theme(db)
    for key, default in THEME_DEFAULTS.items():
        if key not in values:
            continue
        new_val = str(values[key])
        if key in THEME_CHOICES and new_val not in THEME_CHOICES[key]:
            continue
        if key == "contrast":
            try:
                new_val = str(max(0, min(100, int(float(new_val)))))
            except (TypeError, ValueError):
                new_val = default
        if new_val == current.get(key):
            continue
        db_key = f"{_PREFIX}{key}"
        existing = db.get(SettingsOverride, db_key)
        if new_val == default:
            if existing:
                db.delete(existing)
            changed.append(key)
        else:
            if existing:
                existing.value = new_val
                existing.updated_at = utcnow()
            else:
                db.add(SettingsOverride(key=db_key, value=new_val))
            changed.append(key)
    if changed:
        db.commit()
        logger.info("Theme updated: %s", ", ".join(changed))
    return changed


def build_theme_css(theme: dict[str, str]) -> str:
    props: list[str] = []
    dark_props: list[str] = []
    extra_rules: list[str] = []

    color = theme.get("color", THEME_DEFAULTS["color"])
    if color != THEME_DEFAULTS["color"] and color in COLOR_CSS:
        c = COLOR_CSS[color]
        props.extend([f"--tblr-primary:{c['hex']}", f"--tblr-primary-rgb:{c['rgb']}"])

    font = theme.get("font", THEME_DEFAULTS["font"])
    if font != THEME_DEFAULTS["font"] and font in FONT_CSS:
        props.append(f"--tblr-body-font-family:{FONT_CSS[font]}")
    if font == "dyslexia":
        extra_rules.extend(["body{letter-spacing:.018em;word-spacing:.045em;line-height:1.55}", "input,select,textarea,button{letter-spacing:.012em}"])

    base = theme.get("base", THEME_DEFAULTS["base"])
    if base != THEME_DEFAULTS["base"] and base in GRAY_CSS and GRAY_CSS[base]:
        grays = GRAY_CSS[base]
        for step, val in grays.items():
            props.append(f"--tblr-gray-{step}:{val}")
        dark_props.extend([
            f"--tblr-body-color:{grays['200']}", f"--tblr-body-bg:{grays['900']}",
            f"--tblr-secondary-bg:{grays['800']}", f"--tblr-light-text-emphasis:{grays['100']}",
            f"--tblr-dark-text-emphasis:{grays['300']}", f"--tblr-light-bg-subtle:{grays['800']}",
        ])

    radius = theme.get("radius", THEME_DEFAULTS["radius"])
    if radius != THEME_DEFAULTS["radius"]:
        props.append(f"--tblr-border-radius-scale:{radius}")

    epaper = theme.get("epaper", THEME_DEFAULTS["epaper"]) == "true"
    try:
        contrast = max(0, min(100, int(theme.get("contrast", THEME_DEFAULTS["contrast"]))))
    except (TypeError, ValueError):
        contrast = int(THEME_DEFAULTS["contrast"])
    if epaper:
        border = max(24, 220 - round(contrast * 1.7))
        muted = max(0, 112 - round(contrast * 0.9))
        surface = max(238, 255 - round(contrast * 0.12))
        mono_props = [
            "--tblr-primary:#000", "--tblr-primary-rgb:0,0,0", "--tblr-body-color:#000", "--tblr-body-bg:#fff",
            f"--tblr-bg-surface:rgb({surface},{surface},{surface})", f"--tblr-border-color:rgb({border},{border},{border})",
            f"--tblr-secondary-color:rgb({muted},{muted},{muted})", "--tblr-link-color:#000", "--tblr-link-hover-color:#000",
        ]
        props.extend(mono_props)
        dark_props.extend(mono_props)
        extra_rules.extend([
            "html{filter:grayscale(1)}", "body,.page,.page-wrapper{background:#fff!important;color:#000!important}",
            ".card,.dropdown-menu,.modal-content,.navbar,.list-group-item{box-shadow:none!important}",
            f".card,.dropdown-menu,.modal-content,.navbar,.list-group-item,.form-control,.form-select,.btn{{border-color:rgb({border},{border},{border})!important}}",
            f".text-secondary,.form-hint,.card-subtitle{{color:rgb({muted},{muted},{muted})!important}}",
            "[class*=\"bg-\"][class*=\"-lt\"]{background:#fff!important;color:#000!important;border:1px solid #000!important}",
            ".badge{border:1px solid currentColor!important}",
        ])

    if not props and not dark_props and not extra_rules:
        return ""
    parts: list[str] = []
    if props:
        parts.append(":root{" + ";".join(props) + "}")
    if dark_props:
        parts.append("[data-bs-theme=dark]{" + ";".join(dark_props) + "}")
    parts.extend(extra_rules)
    return "".join(parts)
