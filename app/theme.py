"""Theme primitives shared by persisted personal themes and live appearance CSS.

The old global theme storage is retained only as a compatibility API for legacy
callers. Signed-in users never inherit it: personal appearance starts from
THEME_DEFAULTS and is stored per user.
"""

import logging

logger = logging.getLogger(__name__)
_PREFIX = "theme_"

COLOR_CSS = {
    "blue": {"hex": "#066fd1", "rgb": "6,111,209"},
    "azure": {"hex": "#4299e1", "rgb": "66,153,225"},
    "indigo": {"hex": "#4263eb", "rgb": "66,99,235"},
    "purple": {"hex": "#ae3ec9", "rgb": "174,62,201"},
    "pink": {"hex": "#d6336c", "rgb": "214,51,108"},
    "red": {"hex": "#d63939", "rgb": "214,57,57"},
    "orange": {"hex": "#f76707", "rgb": "247,103,7"},
    "yellow": {"hex": "#f59f00", "rgb": "245,159,0"},
    "lime": {"hex": "#74b816", "rgb": "116,184,22"},
    "green": {"hex": "#2fb344", "rgb": "47,179,68"},
    "teal": {"hex": "#0ca678", "rgb": "12,166,120"},
    "cyan": {"hex": "#17a2b8", "rgb": "23,162,184"},
}

FONT_CSS = {
    "sans-serif": '"Inter Var",Inter,-apple-system,BlinkMacSystemFont,San Francisco,Segoe UI,Roboto,Helvetica Neue,sans-serif',
    "serif": "Georgia,Times New Roman,times,serif",
    "monospace": "Monaco,Consolas,Liberation Mono,Courier New,monospace",
    "comic": "Comic Sans MS,Comic Sans,Chalkboard SE,Comic Neue,sans-serif,cursive",
    "dyslexia": 'OpenDyslexic,"Atkinson Hyperlegible",Verdana,Tahoma,Arial,sans-serif',
}

GRAY_CSS = {
    "gray": {"50":"#f9fafb","100":"#f3f4f6","200":"#e5e7eb","300":"#d1d5db","400":"#9ca3af","500":"#6b7280","600":"#4b5563","700":"#374151","800":"#1f2937","900":"#111827","950":"#030712"},
    "slate": {"50":"#f8fafc","100":"#f1f5f9","200":"#e2e8f0","300":"#cbd5e1","400":"#94a3b8","500":"#64748b","600":"#475569","700":"#334155","800":"#1e293b","900":"#0f172a","950":"#020617"},
    "zinc": {"50":"#fafafa","100":"#f4f4f5","200":"#e4e4e7","300":"#d4d4d8","400":"#a1a1aa","500":"#71717a","600":"#52525b","700":"#3f3f46","800":"#27272a","900":"#18181b","950":"#09090b"},
    "neutral": {"50":"#fafafa","100":"#f5f5f5","200":"#e5e5e5","300":"#d4d4d4","400":"#a3a3a3","500":"#737373","600":"#525252","700":"#404040","800":"#262626","900":"#171717","950":"#0a0a0a"},
    "stone": {"50":"#fafaf9","100":"#f5f5f4","200":"#e7e5e4","300":"#d6d3d1","400":"#a8a29e","500":"#78716c","600":"#57534e","700":"#44403c","800":"#292524","900":"#1c1917","950":"#0c0a09"},
}

# Distinct page tints while keeping cards and text on the existing neutral scale.
PAGE_BACKGROUND_CSS = {
    "gray": {"light": "#edf0f4", "dark": "#080e18"},
    "slate": {"light": "#e6eef8", "dark": "#041228"},
    "zinc": {"light": "#eeeaf4", "dark": "#150d20"},
    "neutral": {"light": "#ededed", "dark": "#0e0e0e"},
    "stone": {"light": "#f3e9dc", "dark": "#1c1007"},
}

RADIUS_REM = {"0": 0.0, "0.5": 0.25, "1": 0.5, "1.5": 0.8, "2": 1.1}

THEME_DEFAULTS = {
    "mode": "light",
    # `color` is a read-only legacy alias exposed for old frontend layers.
    "color": "blue",
    "logo_color": "blue",
    "button_color": "blue",
    "font": "sans-serif",
    "base": "gray",
    "radius": "1",
    "epaper": "false",
    "contrast": "65",
    "date_style": "medium",
}

THEME_CHOICES = {
    "mode": ["light", "dark"],
    "color": [*COLOR_CSS.keys(), "rainbow"],
    "logo_color": [*COLOR_CSS.keys(), "rainbow"],
    "button_color": list(COLOR_CSS.keys()),
    "font": list(FONT_CSS.keys()),
    "base": list(GRAY_CSS.keys()),
    "radius": list(RADIUS_REM.keys()),
    "epaper": ["false", "true"],
    "date_style": ["short", "medium", "long"],
}

CANONICAL_PERSONAL_KEYS = (
    "mode", "logo_color", "button_color", "font", "base", "radius",
    "epaper", "contrast", "date_style",
)


def normalize_theme(values: dict | None) -> dict[str, str]:
    """Return one validated canonical theme and migrate the legacy accent key."""
    raw = values if isinstance(values, dict) else {}
    result = {key: str(value) for key, value in THEME_DEFAULTS.items()}

    legacy = str(raw.get("color", THEME_DEFAULTS["color"]))
    logo_default = legacy if legacy in THEME_CHOICES["logo_color"] else THEME_DEFAULTS["logo_color"]
    button_default = legacy if legacy in THEME_CHOICES["button_color"] else THEME_DEFAULTS["button_color"]

    for key in CANONICAL_PERSONAL_KEYS:
        default = THEME_DEFAULTS[key]
        value = raw.get(key, logo_default if key == "logo_color" else button_default if key == "button_color" else default)
        value = str(value)
        if key in THEME_CHOICES and value not in THEME_CHOICES[key]:
            value = default
        if key == "contrast":
            try:
                value = str(max(0, min(100, int(float(value)))))
            except (TypeError, ValueError):
                value = default
        result[key] = value

    # Old scripts may still read theme.color. Keep it fixed/non-rainbow so they
    # cannot reactivate the removed global/rainbow-button controller.
    result["color"] = result["button_color"]
    return result


def get_theme(db) -> dict[str, str]:
    """Legacy global theme reader; signed-in personal appearance does not use it."""
    from app.models import SettingsOverride

    rows = db.query(SettingsOverride).filter(SettingsOverride.key.startswith(_PREFIX)).all()
    overrides = {row.key[len(_PREFIX):]: row.value for row in rows}
    return normalize_theme(overrides)


def save_theme(db, values: dict[str, str]) -> list[str]:
    """Legacy global writer retained for compatibility with old deployments."""
    from app.models import SettingsOverride
    from app.utils import utcnow

    changed: list[str] = []
    current = get_theme(db)
    normalized = normalize_theme({**current, **values})
    for key in CANONICAL_PERSONAL_KEYS:
        if key not in values:
            continue
        new_val = normalized[key]
        if new_val == current.get(key):
            continue
        db_key = f"{_PREFIX}{key}"
        existing = db.get(SettingsOverride, db_key)
        if new_val == THEME_DEFAULTS[key]:
            if existing:
                db.delete(existing)
        elif existing:
            existing.value = new_val
            existing.updated_at = utcnow()
        else:
            db.add(SettingsOverride(key=db_key, value=new_val))
        changed.append(key)
    if changed:
        db.commit()
        logger.info("Legacy global theme updated: %s", ", ".join(changed))
    return changed


def _palette_vars(base: str, mode: str) -> dict[str, str]:
    gray = GRAY_CSS.get(base, GRAY_CSS[THEME_DEFAULTS["base"]])
    page = PAGE_BACKGROUND_CSS.get(base, PAGE_BACKGROUND_CSS[THEME_DEFAULTS["base"]])
    if mode == "dark":
        return {
            "--b2m-page-bg": page["dark"],
            "--b2m-surface-bg": gray["900"],
            "--b2m-surface-secondary": gray["800"],
            "--b2m-input-bg": gray["800"],
            "--b2m-text": gray["100"],
            "--b2m-muted": gray["400"],
            "--b2m-border": gray["700"],
        }
    return {
        "--b2m-page-bg": page["light"],
        "--b2m-surface-bg": "#ffffff",
        "--b2m-surface-secondary": gray["100"],
        "--b2m-input-bg": "#ffffff",
        "--b2m-text": gray["900"],
        "--b2m-muted": gray["600"],
        "--b2m-border": gray["200"],
    }


def _epaper_values(contrast: str, mode: str = "light") -> tuple[int, int, int]:
    try:
        value = max(0, min(100, int(float(contrast))))
    except (TypeError, ValueError):
        value = int(THEME_DEFAULTS["contrast"])
    if mode == "dark":
        # Dark E-paper keeps the page black and uses light cards with black text.
        border = 96 + (159 * value + 50) // 100
        muted = 255
        surface = 184 - (66 * value + 50) // 100
        return border, muted, surface
    # Light mode keeps all text pure black and progressively deepens surfaces.
    border = 170 - (170 * value + 50) // 100
    muted = 0
    surface = 232 - (104 * value + 50) // 100
    return border, muted, surface


def _epaper_surface_secondary(contrast: str, mode: str = "light") -> int:
    try:
        value = max(0, min(100, int(float(contrast))))
    except (TypeError, ValueError):
        value = int(THEME_DEFAULTS["contrast"])
    if mode == "dark":
        return 216 - (64 * value + 50) // 100
    return 216 - (80 * value + 50) // 100


def _epaper_utility_bg(contrast: str, mode: str = "light") -> int:
    try:
        value = max(0, min(100, int(float(contrast))))
    except (TypeError, ValueError):
        value = int(THEME_DEFAULTS["contrast"])
    if mode == "dark":
        return 192 - (32 * value + 50) // 100
    return 208 - (48 * value + 50) // 100


def _css_vars(values: dict[str, str]) -> str:
    return ";".join(f"{key}:{value}" for key, value in values.items())


def _radius_vars(radius: str) -> dict[str, str]:
    r = RADIUS_REM.get(str(radius), RADIUS_REM[THEME_DEFAULTS["radius"]])
    return {
        "--tblr-border-radius-scale": str(radius),
        "--tblr-border-radius": f"{r:g}rem",
        "--tblr-border-radius-sm": f"{max(0, r * .72):g}rem",
        "--tblr-border-radius-lg": f"{max(0, r * 1.45):g}rem",
        "--tblr-border-radius-xl": f"{max(0, r * 1.9):g}rem",
    }


def _button_vars(color: str) -> dict[str, str]:
    selected = COLOR_CSS.get(color, COLOR_CSS[THEME_DEFAULTS["button_color"]])
    return {
        "--tblr-primary": selected["hex"],
        "--tblr-primary-rgb": selected["rgb"],
        "--tblr-link-color": selected["hex"],
        "--tblr-link-hover-color": selected["hex"],
    }


def build_theme_css(theme: dict[str, str]) -> str:
    """Render the complete persisted personal theme used before first paint."""
    t = normalize_theme(theme)
    light = _palette_vars(t["base"], "light")
    dark = _palette_vars(t["base"], "dark")
    common = {}
    common.update(_button_vars(t["button_color"]))
    common.update(_radius_vars(t["radius"]))
    common["--tblr-body-font-family"] = FONT_CSS[t["font"]]
    common["--b2m-saved-mode"] = t["mode"]
    common["--b2m-card-shadow"] = "var(--tblr-box-shadow-card)"
    common["--b2m-page-filter"] = "none"
    light_epaper = _epaper_values(t["contrast"], "light")
    dark_epaper = _epaper_values(t["contrast"], "dark")
    light_secondary = _epaper_surface_secondary(t["contrast"], "light")
    dark_secondary = _epaper_surface_secondary(t["contrast"], "dark")
    light_utility = _epaper_utility_bg(t["contrast"], "light")
    dark_utility = _epaper_utility_bg(t["contrast"], "dark")

    extra: list[str] = []
    logo = t["logo_color"]
    if logo == "rainbow":
        extra.extend([
            "@keyframes b2m-logo-rainbow{0%{background-position:0% 50%}100%{background-position:100% 50%}}",
            ".navbar-brand a .b2m-brand-text{background-image:linear-gradient(90deg,#d63939 0%,#f76707 7.142857%,#f59f00 14.285714%,#2fb344 21.428571%,#17a2b8 28.571429%,#4263eb 35.714286%,#ae3ec9 42.857143%,#d63939 50%,#f76707 57.142857%,#f59f00 64.285714%,#2fb344 71.428571%,#17a2b8 78.571429%,#4263eb 85.714286%,#ae3ec9 92.857143%,#d63939 100%);background-size:200% 100%;background-clip:text;-webkit-background-clip:text;color:transparent!important;-webkit-text-fill-color:transparent!important;animation:b2m-logo-rainbow 12s linear infinite}",
        ])
    else:
        color = COLOR_CSS[logo]["hex"]
        extra.append(f".navbar-brand a{{background:none!important;color:{color}!important;-webkit-text-fill-color:{color}!important;animation:none!important}}")

    if t["font"] == "dyslexia":
        extra.append("body{letter-spacing:.018em;word-spacing:.045em;line-height:1.55}input,select,textarea,button{letter-spacing:.012em}")

    if t["epaper"] == "true":
        light_mono = {
            "--b2m-page-bg": "#ffffff",
            "--b2m-surface-bg": f"rgb({light_epaper[2]},{light_epaper[2]},{light_epaper[2]})",
            "--b2m-surface-secondary": f"rgb({light_secondary},{light_secondary},{light_secondary})",
            "--b2m-input-bg": "#ffffff",
            "--b2m-text": "#000000",
            "--b2m-muted": f"rgb({light_epaper[1]},{light_epaper[1]},{light_epaper[1]})",
            "--b2m-border": f"rgb({light_epaper[0]},{light_epaper[0]},{light_epaper[0]})",
            "--b2m-card-shadow": "none",
            "--b2m-page-filter": "grayscale(1)",
            "--b2m-epaper-border": f"rgb({light_epaper[0]},{light_epaper[0]},{light_epaper[0]})",
            "--b2m-epaper-muted": f"rgb({light_epaper[1]},{light_epaper[1]},{light_epaper[1]})",
            "--b2m-epaper-surface": f"rgb({light_epaper[2]},{light_epaper[2]},{light_epaper[2]})",
            "--b2m-epaper-surface-secondary": f"rgb({light_secondary},{light_secondary},{light_secondary})",
            "--b2m-epaper-utility-bg": f"rgb({light_utility},{light_utility},{light_utility})",
            "--b2m-epaper-utility-text": "#000000",
            "--b2m-epaper-input-bg": "#ffffff",
            "--tblr-primary": "#000000",
            "--tblr-primary-rgb": "0,0,0",
            "--tblr-link-color": "#000000",
            "--tblr-link-hover-color": "#000000",
        }
        dark_mono = {
            "--b2m-page-bg": "#000000",
            "--b2m-surface-bg": f"rgb({dark_epaper[2]},{dark_epaper[2]},{dark_epaper[2]})",
            "--b2m-surface-secondary": f"rgb({dark_secondary},{dark_secondary},{dark_secondary})",
            "--b2m-input-bg": f"rgb({dark_utility},{dark_utility},{dark_utility})",
            "--b2m-text": "#ffffff",
            "--b2m-muted": f"rgb({dark_epaper[1]},{dark_epaper[1]},{dark_epaper[1]})",
            "--b2m-border": f"rgb({dark_epaper[0]},{dark_epaper[0]},{dark_epaper[0]})",
            "--b2m-card-shadow": "none",
            "--b2m-page-filter": "grayscale(1)",
            "--b2m-epaper-border": f"rgb({dark_epaper[0]},{dark_epaper[0]},{dark_epaper[0]})",
            "--b2m-epaper-muted": f"rgb({dark_epaper[1]},{dark_epaper[1]},{dark_epaper[1]})",
            "--b2m-epaper-surface": f"rgb({dark_epaper[2]},{dark_epaper[2]},{dark_epaper[2]})",
            "--b2m-epaper-surface-secondary": f"rgb({dark_secondary},{dark_secondary},{dark_secondary})",
            "--b2m-epaper-utility-bg": f"rgb({dark_utility},{dark_utility},{dark_utility})",
            "--b2m-epaper-utility-text": "#000000",
            "--b2m-epaper-input-bg": f"rgb({dark_utility},{dark_utility},{dark_utility})",
            "--tblr-primary": "#ffffff",
            "--tblr-primary-rgb": "255,255,255",
            "--tblr-link-color": "#ffffff",
            "--tblr-link-hover-color": "#ffffff",
        }
        light = dict(light_mono)
        dark = dict(dark_mono)
        for key in ("--tblr-primary", "--tblr-primary-rgb", "--tblr-link-color", "--tblr-link-hover-color"):
            common.pop(key, None)
    root_values = {**light, **common}
    dark_values = {**dark, **common}
    return ":root{" + _css_vars(root_values) + "}" + "[data-bs-theme=dark]{" + _css_vars(dark_values) + "}" + "".join(extra)


def build_theme_live_catalog_css() -> str:
    """CSS catalog for synchronous unsaved previews with no network roundtrip."""
    rules: list[str] = [
        ":root{--b2m-page-bg:#f9fafb;--b2m-surface-bg:#fff;--b2m-surface-secondary:#f3f4f6;--b2m-input-bg:#fff;--b2m-text:#111827;--b2m-muted:#4b5563;--b2m-border:#e5e7eb;--b2m-card-shadow:var(--tblr-box-shadow-card);--b2m-page-filter:none}",
        "html{filter:var(--b2m-page-filter,none)}",
        "body,.page,.page-wrapper,.page-body{background-color:var(--b2m-page-bg)!important;color:var(--b2m-text)!important}",
        ".navbar,.card,.dropdown-menu,.modal-content,.offcanvas,.toast,.list-group-item{background-color:var(--b2m-surface-bg)!important;color:var(--b2m-text)!important;border-color:var(--b2m-border)!important}",
        ".card{box-shadow:var(--b2m-card-shadow,var(--tblr-box-shadow-card))!important}",
        ".card-header,.card-footer,.dropdown-header,.table thead th{background-color:var(--b2m-surface-secondary)!important;border-color:var(--b2m-border)!important}",
        ".form-control,.form-select,.input-group-text,.form-selectgroup-label{background-color:var(--b2m-input-bg)!important;color:var(--b2m-text)!important;border-color:var(--b2m-border)!important}",
        ".table,.table>thead,.table>tbody,.table>tfoot,.table>tr,.table>td,.table>th{--tblr-table-color:var(--b2m-text);--tblr-table-bg:transparent;color:var(--b2m-text)!important;border-color:var(--b2m-border)!important}",
        ".text-secondary,.text-muted,.form-hint,.card-subtitle{color:var(--b2m-muted)!important}",
        ":root{--tblr-body-bg:var(--b2m-page-bg);--tblr-body-color:var(--b2m-text);--tblr-bg-surface:var(--b2m-surface-bg);--tblr-bg-surface-secondary:var(--b2m-surface-secondary);--tblr-border-color:var(--b2m-border);--tblr-secondary-color:var(--b2m-muted)}",
        "a[href=\"/settings?tab=appearance\"]{display:none!important}",
        "h4.subheader:has(+ .list-group > a[href=\"/settings?tab=appearance\"]){display:none!important}",
        ".list-group:has(> a[href=\"/settings?tab=appearance\"]:only-child){display:none!important}",
        ".b2m-rainbow-swatch{background:linear-gradient(135deg,#d63939,#f59f00,#2fb344,#17a2b8,#4263eb,#ae3ec9)!important}",
    ]

    for base in THEME_CHOICES["base"]:
        rules.append(f'html[data-b2m-base="{base}"]{{{_css_vars(_palette_vars(base, "light"))}}}')
        rules.append(f'html[data-bs-theme=dark][data-b2m-base="{base}"]{{{_css_vars(_palette_vars(base, "dark"))}}}')

    for name, color in COLOR_CSS.items():
        rules.append(f'html[data-b2m-button-color="{name}"]{{{_css_vars(_button_vars(name))}}}')
        rules.append(f'html[data-b2m-logo-color="{name}"] .navbar-brand a{{background:none!important;color:{color["hex"]}!important;-webkit-text-fill-color:{color["hex"]}!important;animation:none!important}}')
    rules.extend([
        "@keyframes b2m-logo-rainbow-live{0%{background-position:0% 50%}100%{background-position:100% 50%}}",
        'html[data-b2m-logo-color="rainbow"] .navbar-brand a .b2m-brand-text{background:linear-gradient(90deg,#d63939 0%,#f76707 7.142857%,#f59f00 14.285714%,#2fb344 21.428571%,#17a2b8 28.571429%,#4263eb 35.714286%,#ae3ec9 42.857143%,#d63939 50%,#f76707 57.142857%,#f59f00 64.285714%,#2fb344 71.428571%,#17a2b8 78.571429%,#4263eb 85.714286%,#ae3ec9 92.857143%,#d63939 100%)!important;background-size:200% 100%!important;background-clip:text!important;-webkit-background-clip:text!important;color:transparent!important;-webkit-text-fill-color:transparent!important;animation:b2m-logo-rainbow-live 12s linear infinite!important}',
    ])

    for name, family in FONT_CSS.items():
        rules.append(f'html[data-b2m-font="{name}"]{{--tblr-body-font-family:{family}}}')
    for name in THEME_CHOICES["radius"]:
        rules.append(f'html[data-b2m-radius="{name}"]{{{_css_vars(_radius_vars(name))}}}')

    rules.extend([
        'html[data-b2m-epaper="true"]{--b2m-page-bg:#fff;--b2m-surface-bg:var(--b2m-epaper-surface,#e8e8e8);--b2m-surface-secondary:var(--b2m-epaper-surface-secondary,#d8d8d8);--b2m-epaper-utility-bg:#d0d0d0;--b2m-epaper-utility-text:#000;--b2m-input-bg:#fff;--b2m-text:#000;--b2m-muted:var(--b2m-epaper-muted,#000);--b2m-border:var(--b2m-epaper-border,#000);--b2m-card-shadow:none;--b2m-page-filter:grayscale(1);--tblr-primary:#000;--tblr-primary-rgb:0,0,0;--tblr-link-color:#000;--tblr-link-hover-color:#000}',
        'html[data-bs-theme=dark][data-b2m-epaper="true"]{--b2m-page-bg:#000;--b2m-surface-bg:var(--b2m-epaper-surface,#505050);--b2m-surface-secondary:var(--b2m-epaper-surface-secondary,#d8d8d8);--b2m-epaper-utility-bg:#c0c0c0;--b2m-epaper-utility-text:#000;--b2m-epaper-input-bg:var(--b2m-epaper-utility-bg,#c0c0c0);--b2m-input-bg:var(--b2m-epaper-input-bg);--b2m-text:#fff;--b2m-muted:var(--b2m-epaper-muted,#fff);--b2m-border:var(--b2m-epaper-border,#fff);--b2m-card-shadow:none;--tblr-primary:#fff;--tblr-primary-rgb:255,255,255;--tblr-link-color:#fff;--tblr-link-hover-color:#fff}',
        'html[data-b2m-epaper="false"]{--b2m-page-filter:none}',
    ])
    return "".join(rules)
