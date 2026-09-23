"""Theme settings — global defaults and deterministic CSS rendering."""

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
    "color": ["blue", "azure", "indigo", "purple", "pink", "red", "orange", "yellow", "lime", "green", "teal", "cyan", "rainbow"],
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

# One canonical neutral palette table is used by server-rendered CSS and mirrored
# by the browser live renderer. ui-v29 previously used a second, stronger table
# after load, which caused a visible background jump on every navigation.
GRAY_CSS = {
    "gray":{"50":"#f7f8fa","100":"#eceff3","200":"#d8dde5","300":"#b9c1cc","400":"#8f9aa8","500":"#687483","600":"#4c5765","700":"#37414d","800":"#242c35","900":"#171d24","950":"#0b0f14"},
    "slate":{"50":"#f6f8fb","100":"#e8eef6","200":"#d2ddea","300":"#afc0d4","400":"#7f96b0","500":"#5a7390","600":"#405870","700":"#2e4258","800":"#1d2d3e","900":"#111d2a","950":"#08111c"},
    "zinc":{"50":"#fafafa","100":"#eeeeef","200":"#d9d9dc","300":"#bdbdc3","400":"#97979f","500":"#707078","600":"#515158","700":"#3a3a40","800":"#25252a","900":"#17171b","950":"#0b0b0e"},
    "neutral":{"50":"#fbfbfb","100":"#f0f0f0","200":"#d8d8d8","300":"#b9b9b9","400":"#929292","500":"#6d6d6d","600":"#4f4f4f","700":"#393939","800":"#242424","900":"#151515","950":"#080808"},
    "stone":{"50":"#fbf9f6","100":"#f0ebe5","200":"#ddd4ca","300":"#c1b3a4","400":"#9b8977","500":"#796856","600":"#5a4d41","700":"#443a32","800":"#2d2722","900":"#1c1815","950":"#0e0c0a"},
}

RADIUS_REM = {"0":0.0, "0.5":0.25, "1":0.5, "1.5":0.8, "2":1.1}


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

    epaper = theme.get("epaper", THEME_DEFAULTS["epaper"]) == "true"
    color = theme.get("color", THEME_DEFAULTS["color"])
    if color == "rainbow" and not epaper:
        extra_rules.extend([
            "@keyframes b2m-rainbow-accent{0%,100%{--tblr-primary:#d63939;--tblr-primary-rgb:214,57,57}16%{--tblr-primary:#f76707;--tblr-primary-rgb:247,103,7}33%{--tblr-primary:#f59f00;--tblr-primary-rgb:245,159,0}50%{--tblr-primary:#2fb344;--tblr-primary-rgb:47,179,68}66%{--tblr-primary:#17a2b8;--tblr-primary-rgb:23,162,184}83%{--tblr-primary:#ae3ec9;--tblr-primary-rgb:174,62,201}}",
            ":root{animation:b2m-rainbow-accent 14s linear infinite}",
            "@keyframes b2m-rainbow-brand-move{0%{background-position:0% 50%}100%{background-position:200% 50%}}",
            ".b2m-brand-text{background:linear-gradient(90deg,#d63939,#f76707,#f59f00,#2fb344,#17a2b8,#4263eb,#ae3ec9,#d63939);background-size:200% 100%;background-clip:text;-webkit-background-clip:text;color:transparent!important;-webkit-text-fill-color:transparent;animation:b2m-rainbow-brand-move 12s linear infinite}",
        ])
    elif color != THEME_DEFAULTS["color"] and color in COLOR_CSS:
        c = COLOR_CSS[color]
        props.extend([f"--tblr-primary:{c['hex']}", f"--tblr-primary-rgb:{c['rgb']}"])

    font = theme.get("font", THEME_DEFAULTS["font"])
    if font != THEME_DEFAULTS["font"] and font in FONT_CSS:
        props.append(f"--tblr-body-font-family:{FONT_CSS[font]}")
    if font == "dyslexia":
        extra_rules.extend(["body{letter-spacing:.018em;word-spacing:.045em;line-height:1.55}", "input,select,textarea,button{letter-spacing:.012em}"])

    base = theme.get("base", THEME_DEFAULTS["base"])
    grays = GRAY_CSS.get(base, GRAY_CSS[THEME_DEFAULTS["base"]])
    for step, val in grays.items():
        props.append(f"--tblr-gray-{step}:{val}")
    props.extend([
        f"--tblr-body-color:{grays['900']}",
        f"--tblr-body-bg:{grays['100']}",
        f"--tblr-bg-surface:{grays['50']}",
        f"--tblr-bg-surface-secondary:{grays['200']}",
        f"--tblr-secondary-bg:{grays['200']}",
        f"--tblr-border-color:{grays['300']}",
        f"--tblr-secondary-color:{grays['600']}",
    ])
    dark_props.extend([
        f"--tblr-body-color:{grays['100']}",
        f"--tblr-body-bg:{grays['950']}",
        f"--tblr-bg-surface:{grays['900']}",
        f"--tblr-bg-surface-secondary:{grays['800']}",
        f"--tblr-secondary-bg:{grays['800']}",
        f"--tblr-border-color:{grays['700']}",
        f"--tblr-secondary-color:{grays['400']}",
        f"--tblr-light-text-emphasis:{grays['100']}",
        f"--tblr-dark-text-emphasis:{grays['300']}",
        f"--tblr-light-bg-subtle:{grays['800']}",
    ])

    radius = str(theme.get("radius", THEME_DEFAULTS["radius"]))
    radius_rem = RADIUS_REM.get(radius, RADIUS_REM[THEME_DEFAULTS["radius"]])
    props.extend([
        f"--tblr-border-radius-scale:{radius}",
        f"--tblr-border-radius:{radius_rem}rem",
        f"--tblr-border-radius-sm:{max(0.0, radius_rem * 0.72)}rem",
        f"--tblr-border-radius-lg:{max(0.0, radius_rem * 1.45)}rem",
        f"--tblr-border-radius-xl:{max(0.0, radius_rem * 1.9)}rem",
    ])

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
            f"--tblr-bg-surface:rgb({surface},{surface},{surface})", f"--tblr-bg-surface-secondary:rgb({surface},{surface},{surface})",
            f"--tblr-secondary-bg:rgb({surface},{surface},{surface})", f"--tblr-border-color:rgb({border},{border},{border})",
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

    parts: list[str] = []
    if props:
        parts.append(":root{" + ";".join(props) + "}")
    if dark_props:
        parts.append("[data-bs-theme=dark]{" + ";".join(dark_props) + "}")
    parts.extend(extra_rules)
    return "".join(parts)
