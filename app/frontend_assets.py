from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from app.theme import GRAY_CSS, PAGE_BACKGROUND_CSS, THEME_CHOICES, THEME_DEFAULTS, build_theme_live_catalog_css

STATIC_DIR = Path(__file__).resolve().parent / "static"
GENERATED_DIR = STATIC_DIR / "generated"

GLOBAL_CSS = (
    "css/ui-v2.css",
    "css/ui-v4.css",
    "css/ui-v6.css",
    "css/ui-v9.css",
    "css/ui-v17.css",
    "css/ui-v22.css",
    "css/ui-v23.css",
    "css/ui-v24.css",
    "css/ui-v25.css",
    "css/ui-v27.css",
    "css/ui-v28.css",
    "css/ui-v29.css",
)
LABEL_CSS = ("css/ui-v13.css",)

# v35 must initialize first so every historical UI layer can detect that it no
# longer owns appearance. Their non-theme responsibilities remain active.
GLOBAL_JS = (
    "js/theme-controls-v32.js",
    "js/ui-v4.js",
    "js/ui-v6.js",
    "js/ui-v9.js",
    "js/ui-v23.js",
    "js/ui-v24.js",
    "js/ui-v25.js",
    "js/ui-v26.js",
    "js/ui-v27.js",
    "js/regression-v28.js",
    "js/ui-v29.js",
    "js/terminology-v30.js",
    "js/shopping-bootstrap-v31.js",
    "js/ui-v12-bell.js",
)
LABEL_JS = (
    "js/labels-b21.js",
    "js/labels-b21-v2.js",
    "js/labels-b21-v2-patch.js",
    "js/labels-b21-v4.js",
    "js/ui-v13-fixes.js",
    "js/labels-v18.js",
    "js/labels-v22.js",
    "js/labels-v23.js",
    "js/labels-v24.js",
    "js/labels-scope-v32.js",
    "js/labels-fixes-v30.js",
)

BUNDLES = {
    "global-ui.css": GLOBAL_CSS,
    "labels-ui.css": LABEL_CSS,
    "global-ui.js": GLOBAL_JS,
    "labels-ui.js": LABEL_JS,
}


def _v35_surface_vars(base: str, mode: str) -> dict[str, str]:
    """Return private v35 surface values with no dependency on legacy vars."""
    gray = GRAY_CSS.get(base, GRAY_CSS[THEME_DEFAULTS["base"]])
    page = PAGE_BACKGROUND_CSS.get(base, PAGE_BACKGROUND_CSS[THEME_DEFAULTS["base"]])
    if mode == "dark":
        return {
            "--b2m-v35-page-bg": page["dark"],
            "--b2m-v35-surface-bg": gray["900"],
            "--b2m-v35-surface-secondary": gray["800"],
            "--b2m-v35-input-bg": gray["800"],
            "--b2m-v35-text": gray["100"],
            "--b2m-v35-muted": gray["400"],
            "--b2m-v35-border": gray["700"],
        }
    return {
        "--b2m-v35-page-bg": page["light"],
        "--b2m-v35-surface-bg": "#ffffff",
        "--b2m-v35-surface-secondary": gray["100"],
        "--b2m-v35-input-bg": "#ffffff",
        "--b2m-v35-text": gray["900"],
        "--b2m-v35-muted": gray["600"],
        "--b2m-v35-border": gray["200"],
    }


def _css_vars(values: dict[str, str]) -> str:
    return ";".join(f"{key}:{value}" for key, value in values.items())


_EPAPER_SEMANTIC_COLORS = (
    "primary", "secondary", "success", "info", "warning", "danger", "light",
    "dark", "blue", "azure", "indigo", "purple", "pink", "red", "orange",
    "yellow", "lime", "green", "teal", "cyan",
)


def _v35_epaper_vars(mode: str) -> dict[str, str]:
    dark = mode == "dark"
    text = "#fff" if dark else "#000"
    text_rgb = "255,255,255" if dark else "0,0,0"
    action_bg = text
    action_text = "#000" if dark else "#fff"
    values = {
        "--b2m-v35-page-bg": "#000" if dark else "#fff",
        "--b2m-v35-surface-bg": "var(--b2m-epaper-surface,#b8b8b8)" if dark else "var(--b2m-epaper-surface,#e8e8e8)",
        "--b2m-v35-surface-secondary": "var(--b2m-epaper-surface-secondary,#d8d8d8)" if dark else "var(--b2m-epaper-surface-secondary,#d8d8d8)",
        "--b2m-v35-utility-bg": "var(--b2m-epaper-utility-bg,#c0c0c0)" if dark else "var(--b2m-epaper-utility-bg,#d0d0d0)",
        "--b2m-v35-utility-text": "#000",
        "--b2m-v35-input-bg": "var(--b2m-epaper-input-bg,var(--b2m-epaper-utility-bg,#c0c0c0))" if dark else "#fff",
        "--b2m-v35-text": text,
        "--b2m-v35-muted": "var(--b2m-epaper-muted," + text + ")",
        "--b2m-v35-border": "var(--b2m-epaper-border," + text + ")",
        "--b2m-v35-card-shadow": "none",
        "--b2m-v35-action-bg": action_bg,
        "--b2m-v35-action-text": action_text,
        "--tblr-primary": text,
        "--tblr-primary-rgb": text_rgb,
        "--tblr-link-color": text,
        "--tblr-link-hover-color": text,
        "--tblr-body-bg": "var(--b2m-v35-page-bg)",
        "--tblr-body-color": "var(--b2m-v35-text)",
        "--tblr-bg-surface": "var(--b2m-v35-surface-bg)",
        "--tblr-bg-surface-secondary": "var(--b2m-v35-surface-secondary)",
        "--tblr-border-color": "var(--b2m-v35-border)",
        "--tblr-border-color-translucent": "var(--b2m-v35-border)",
        "--tblr-secondary-color": "var(--b2m-v35-text)",
    }
    for color in _EPAPER_SEMANTIC_COLORS:
        values[f"--tblr-{color}"] = text
        values[f"--tblr-{color}-rgb"] = text_rgb
        values[f"--tblr-{color}-lt"] = "var(--b2m-v35-utility-bg)"
        values[f"--tblr-{color}-fg"] = text
        values[f"--tblr-{color}-dark"] = text
    return values


def _build_v35_surface_catalog_css() -> str:
    """Generate direct root-state selectors used only by the v35 renderer."""
    rules = [
        "html{" + _css_vars(_v35_surface_vars(THEME_DEFAULTS["base"], "light")) + ";--b2m-v35-card-shadow:var(--tblr-box-shadow-card)}"
    ]
    for base in THEME_CHOICES["base"]:
        rules.append(
            f'html[data-b2m-base="{base}"]{{{_css_vars(_v35_surface_vars(base, "light"))}}}'
        )
        rules.append(
            f'html[data-bs-theme="dark"][data-b2m-base="{base}"]{{{_css_vars(_v35_surface_vars(base, "dark"))}}}'
        )
    light_epaper = _css_vars(_v35_epaper_vars("light"))
    dark_epaper = _css_vars(_v35_epaper_vars("dark"))
    rules.extend([
        f'html[data-b2m-epaper="true"]{{{light_epaper}}}',
        f'html[data-bs-theme="dark"][data-b2m-epaper="true"]{{{dark_epaper}}}',
    ])
    return "".join(rules)


# Historical CSS may still declare the old --b2m-* variables on descendants.
# The visible v35 surfaces therefore consume only collision-free private values
# that are written directly on <html> by the catalog above.
APPEARANCE_AUTHORITY_CSS = """
html body,
html body .page,
html body .page-wrapper,
html body .page-body {
  background: var(--b2m-v35-page-bg) !important;
  color: var(--b2m-v35-text) !important;
}
html body .navbar,
html body .card,
html body .dropdown-menu,
html body .modal-content,
html body .offcanvas,
html body .toast,
html body .list-group-item {
  background: var(--b2m-v35-surface-bg) !important;
  color: var(--b2m-v35-text) !important;
  border-color: var(--b2m-v35-border) !important;
}
html body .card {
  box-shadow: var(--b2m-v35-card-shadow, var(--tblr-box-shadow-card)) !important;
}
html body .card-header,
html body .card-footer,
html body .dropdown-header,
html body .table thead th {
  background: var(--b2m-v35-surface-secondary) !important;
  color: var(--b2m-v35-text) !important;
  border-color: var(--b2m-v35-border) !important;
}
html body .form-control,
html body .form-select,
html body .input-group-text,
html body .form-selectgroup-label {
  background: var(--b2m-v35-input-bg) !important;
  color: var(--b2m-v35-text) !important;
  border-color: var(--b2m-v35-border) !important;
}
/* Preserve radio selection states over the generic input surface rules. */
html body .form-selectgroup-input:checked + .form-selectgroup-label {
  background: color-mix(in srgb, var(--tblr-primary) 14%, var(--b2m-v35-input-bg)) !important;
  color: var(--b2m-v35-text) !important;
  border-color: var(--tblr-primary) !important;
  box-shadow: inset 0 0 0 1px var(--tblr-primary) !important;
}
html body .form-selectgroup-input:focus-visible + .form-selectgroup-label {
  outline: 2px solid var(--tblr-primary);
  outline-offset: 2px;
}
html body .table,
html body .table > :not(caption) > * > * {
  background-color: transparent !important;
  color: var(--b2m-v35-text) !important;
  border-color: var(--b2m-v35-border) !important;
}
html body .text-secondary,
html body .text-muted,
html body .form-hint,
html body .card-subtitle {
  color: var(--b2m-v35-muted) !important;
}
/* E-paper replaces colored text, icons, borders and action fills with monochrome. */
html[data-b2m-epaper="true"] body * {
  color: var(--b2m-v35-text) !important;
  border-color: var(--b2m-v35-border) !important;
}
html[data-b2m-epaper="true"] body a,
html[data-b2m-epaper="true"] body [class*="btn-outline-"] {
  color: var(--b2m-v35-action-bg) !important;
}
html[data-b2m-epaper="true"] body [class*="bg-"]:not(.bg-transparent):not(.bg-white):not(.bg-body):not([class*="bg-body"]) {
  background: var(--b2m-v35-utility-bg) !important;
  background-image: none !important;
  border-color: var(--b2m-v35-border) !important;
  color: var(--b2m-v35-utility-text) !important;
}
html[data-b2m-epaper="true"] body .avatar,
html[data-b2m-epaper="true"] body .badge,
html[data-b2m-epaper="true"] body .alert,
html[data-b2m-epaper="true"] body [class*="alert-"],
html[data-b2m-epaper="true"] body .status,
html[data-b2m-epaper="true"] body mark {
  background: var(--b2m-v35-utility-bg) !important;
  background-image: none !important;
  border-color: var(--b2m-v35-border) !important;
  color: var(--b2m-v35-utility-text) !important;
}
html[data-b2m-epaper="true"] body [class*="bg-"] *,
html[data-b2m-epaper="true"] body .avatar *,
html[data-b2m-epaper="true"] body .badge *,
html[data-b2m-epaper="true"] body .alert *,
html[data-b2m-epaper="true"] body [class*="alert-"] *,
html[data-b2m-epaper="true"] body .status *,
html[data-b2m-epaper="true"] body mark * {
  color: var(--b2m-v35-utility-text) !important;
}
html[data-b2m-epaper="true"] body [class*="text-"]:not(.text-reset) {
  color: var(--b2m-v35-text) !important;
}

/* Text classes and high-specificity legacy item avatars must not undo the
   black foreground used on light monochrome utility tiles. */
html[data-b2m-epaper="true"] body [class*="bg-"]:not(.bg-transparent):not(.bg-white):not(.bg-body):not([class*="bg-body"]),
html[data-b2m-epaper="true"] body .avatar[class*="text-"],
html[data-b2m-epaper="true"] body .badge[class*="text-"],
html[data-b2m-epaper="true"] body .alert[class*="text-"],
html[data-b2m-epaper="true"] body .status[class*="text-"],
html[data-b2m-epaper="true"] body mark[class*="text-"],
html[data-b2m-epaper="true"] body .card:has(#item-stat-total) .avatar,
html[data-b2m-epaper="true"] body .card:has(#item-stat-7) .avatar,
html[data-b2m-epaper="true"] body .card:has(#item-stat-30) .avatar,
html[data-b2m-epaper="true"] body .card:has(#item-stat-last) .avatar {
  color: var(--b2m-v35-utility-text) !important;
}
html[data-b2m-epaper="true"] body [class*="bg-"]:not(.bg-transparent):not(.bg-white):not(.bg-body):not([class*="bg-body"]) [class*="text-"],
html[data-b2m-epaper="true"] body .avatar [class*="text-"],
html[data-b2m-epaper="true"] body .badge [class*="text-"],
html[data-b2m-epaper="true"] body .alert [class*="text-"],
html[data-b2m-epaper="true"] body .status [class*="text-"],
html[data-b2m-epaper="true"] body mark [class*="text-"],
html[data-b2m-epaper="true"] body .card:has(#item-stat-total) .avatar *,
html[data-b2m-epaper="true"] body .card:has(#item-stat-7) .avatar *,
html[data-b2m-epaper="true"] body .card:has(#item-stat-30) .avatar *,
html[data-b2m-epaper="true"] body .card:has(#item-stat-last) .avatar * {
  color: var(--b2m-v35-utility-text) !important;
}

/* The secondary surface is a light tile in both E-paper palettes; use a
   black foreground there, while preserving native input and button colors. */
html[data-b2m-epaper="true"] body .card-header,
html[data-b2m-epaper="true"] body .card-footer,
html[data-b2m-epaper="true"] body .dropdown-header,
html[data-b2m-epaper="true"] body .table thead th {
  color: var(--b2m-v35-utility-text) !important;
}
html[data-b2m-epaper="true"] body .card-header *:not(input):not(select):not(textarea):not(.form-control):not(.form-select),
html[data-b2m-epaper="true"] body .card-footer *:not(input):not(select):not(textarea):not(.form-control):not(.form-select),
html[data-b2m-epaper="true"] body .dropdown-header *:not(input):not(select):not(textarea):not(.form-control):not(.form-select),
html[data-b2m-epaper="true"] body .table thead th *:not(input):not(select):not(textarea):not(.form-control):not(.form-select) {
  color: var(--b2m-v35-utility-text) !important;
}
html[data-b2m-epaper="true"] body .bg-white,
html[data-b2m-epaper="true"] body [class*="bg-body"] {
  background-color: var(--b2m-v35-surface-bg) !important;
  background-image: none !important;
  color: var(--b2m-v35-text) !important;
}
html[data-b2m-epaper="true"] body .btn:not(.btn-link):not([class*="btn-outline-"]),
html[data-b2m-epaper="true"] body .btn-check:checked + .btn,
html[data-b2m-epaper="true"] body .dropdown-item.active,
html[data-b2m-epaper="true"] body .list-group-item.active,
html[data-b2m-epaper="true"] body .nav-link.active,
html[data-b2m-epaper="true"] body .progress-bar {
  background: var(--b2m-v35-action-bg) !important;
  background-image: none !important;
  border-color: var(--b2m-v35-action-bg) !important;
  color: var(--b2m-v35-action-text) !important;
}
html[data-b2m-epaper="true"] body .btn:hover,
html[data-b2m-epaper="true"] body .btn:focus,
html[data-b2m-epaper="true"] body .btn:active,
html[data-b2m-epaper="true"] body [class*="btn-outline-"]:hover,
html[data-b2m-epaper="true"] body [class*="btn-outline-"]:focus,
html[data-b2m-epaper="true"] body [class*="btn-outline-"]:active {
  background: var(--b2m-v35-action-bg) !important;
  background-image: none !important;
  border-color: var(--b2m-v35-action-bg) !important;
  color: var(--b2m-v35-action-text) !important;
}
html[data-b2m-epaper="true"] body .btn:not(.btn-link):not([class*="btn-outline-"]) *,
html[data-b2m-epaper="true"] body .btn-check:checked + .btn *,
html[data-b2m-epaper="true"] body .dropdown-item.active *,
html[data-b2m-epaper="true"] body .list-group-item.active *,
html[data-b2m-epaper="true"] body .nav-link.active *,
html[data-b2m-epaper="true"] body .btn:hover *,
html[data-b2m-epaper="true"] body .btn:focus *,
html[data-b2m-epaper="true"] body .btn:active *,
html[data-b2m-epaper="true"] body [class*="btn-outline-"]:hover *,
html[data-b2m-epaper="true"] body [class*="btn-outline-"]:focus *,
html[data-b2m-epaper="true"] body [class*="btn-outline-"]:active * {
  color: var(--b2m-v35-action-text) !important;
}
html[data-b2m-epaper="true"] body .btn-link *,
html[data-b2m-epaper="true"] body [class*="btn-outline-"] * {
  color: var(--b2m-v35-action-bg) !important;
}
html[data-b2m-epaper="true"] body svg {
  color: var(--b2m-v35-text) !important;
}
html[data-b2m-epaper="true"] body svg[fill]:not([fill="none"]),
html[data-b2m-epaper="true"] body svg [fill]:not([fill="none"]) {
  fill: currentColor !important;
}
html[data-b2m-epaper="true"] body svg[stroke]:not([stroke="none"]),
html[data-b2m-epaper="true"] body svg [stroke]:not([stroke="none"]) {
  stroke: currentColor !important;
}

/* Status marks are black or white too, so their state does not disappear into
   a colored or low-contrast fill. */
html[data-b2m-epaper="true"] body .status-indicator {
  --tblr-status-color: var(--b2m-v35-action-bg) !important;
}
html[data-b2m-epaper="true"] body .status-indicator-circle,
html[data-b2m-epaper="true"] body .status-dot {
  background: var(--b2m-v35-action-bg) !important;
}
html[data-b2m-epaper="true"] body [class*="bg-"]:not(.bg-transparent):not(.bg-white):not(.bg-body):not([class*="bg-body"]) svg,
html[data-b2m-epaper="true"] body .avatar svg,
html[data-b2m-epaper="true"] body .badge svg,
html[data-b2m-epaper="true"] body .alert svg,
html[data-b2m-epaper="true"] body .status svg,
html[data-b2m-epaper="true"] body mark svg {
  color: var(--b2m-v35-utility-text) !important;
}
html[data-b2m-epaper="true"] body .card:has(#item-stat-total) .avatar,
html[data-b2m-epaper="true"] body .card:has(#item-stat-7) .avatar,
html[data-b2m-epaper="true"] body .card:has(#item-stat-30) .avatar,
html[data-b2m-epaper="true"] body .card:has(#item-stat-last) .avatar {
  background: var(--b2m-v35-utility-bg) !important;
  background-image: none !important;
}
html[data-b2m-epaper="true"].b2m-epaper-v9 body .b2m-brand-text {
  background: none !important;
  color: var(--b2m-v35-text) !important;
  -webkit-text-fill-color: var(--b2m-v35-text) !important;
  animation: none !important;
}
html[data-b2m-epaper="true"].b2m-epaper-v9 body .b2m-scan-link-card {
  background: var(--b2m-v35-surface-bg) !important;
  border-color: var(--b2m-v35-border) !important;
}
html[data-b2m-epaper="true"].b2m-epaper-v9 body #activity-table tbody tr[data-href]:hover > td {
  background: var(--b2m-v35-surface-secondary) !important;
}
html[data-b2m-epaper="true"].b2m-epaper-v9 body #notif-dropdown > a.nav-link.b2m-v12-bell-flash {
  background: var(--b2m-v35-utility-bg) !important;
  outline-color: var(--b2m-v35-text) !important;
  box-shadow: inset 0 0 0 1px var(--b2m-v35-text), 0 0 0 2px transparent !important;
}
html[data-b2m-epaper="true"].b2m-epaper-v9 body #notif-dropdown > a.nav-link.b2m-v12-bell-flash > .b2m-stable-bell {
  color: var(--b2m-v35-text) !important;
}
html[data-b2m-epaper="true"] body input,
html[data-b2m-epaper="true"] body progress {
  accent-color: var(--b2m-v35-action-bg) !important;
}
html[data-b2m-epaper="true"] body input::placeholder,
html[data-b2m-epaper="true"] body textarea::placeholder {
  color: var(--b2m-v35-text) !important;
  opacity: .75 !important;
}
/* Theme switches update every surface in the same frame. */
html body, html body .page, html body .page-wrapper, html body .page-body,
html body .navbar, html body .card, html body .dropdown-menu,
html body .modal-content, html body .list-group-item,
html body .form-control, html body .form-select,
html body .form-selectgroup-label, html body .input-group-text {
  transition: none !important;
}
html[data-b2m-epaper="true"] body * {
  transition: none !important;
}
/* Dark e-paper keeps the page black, while readable components are inverted. */
html[data-bs-theme="dark"][data-b2m-epaper="true"] body .navbar,
html[data-bs-theme="dark"][data-b2m-epaper="true"] body .card,
html[data-bs-theme="dark"][data-b2m-epaper="true"] body .dropdown-menu,
html[data-bs-theme="dark"][data-b2m-epaper="true"] body .modal-content,
html[data-bs-theme="dark"][data-b2m-epaper="true"] body .offcanvas,
html[data-bs-theme="dark"][data-b2m-epaper="true"] body .toast,
html[data-bs-theme="dark"][data-b2m-epaper="true"] body .list-group-item,
html[data-bs-theme="dark"][data-b2m-epaper="true"] body .card :is(h1,h2,h3,h4,h5,h6,p,span,small,strong,em,label,a,td,th,li,div),
html[data-bs-theme="dark"][data-b2m-epaper="true"] body .navbar :is(span,small,strong,a,i,svg),
html[data-bs-theme="dark"][data-b2m-epaper="true"] body .dropdown-menu *,
html[data-bs-theme="dark"][data-b2m-epaper="true"] body .modal-content *,
html[data-bs-theme="dark"][data-b2m-epaper="true"] body .offcanvas *,
html[data-bs-theme="dark"][data-b2m-epaper="true"] body .toast *,
html[data-bs-theme="dark"][data-b2m-epaper="true"] body .list-group-item * {
  color: #000 !important;
}
html[data-bs-theme="dark"][data-b2m-epaper="true"] body .card .status-indicator-circle,
html[data-bs-theme="dark"][data-b2m-epaper="true"] body .card .status-dot {
  background-color: #000 !important;
}
html[data-bs-theme="dark"][data-b2m-epaper="true"] body .navbar .navbar-brand a {
  background: none !important;
  color: #000 !important;
  -webkit-text-fill-color: #000 !important;
  animation: none !important;
}

/* Light e-paper filled buttons keep white labels and glyphs above utility text rules. */
html[data-b2m-epaper="true"][data-bs-theme="light"] body .btn:not(.btn-link):not([class*="btn-outline-"]),
html[data-b2m-epaper="true"][data-bs-theme="light"] body .btn:not(.btn-link):not([class*="btn-outline-"]) *,
html[data-b2m-epaper="true"][data-bs-theme="light"] body .btn:not(.btn-link):not([class*="btn-outline-"]) svg,
html[data-b2m-epaper="true"][data-bs-theme="light"] body .btn:not(.btn-link):not([class*="btn-outline-"]) svg * {
  color: #fff !important;
  -webkit-text-fill-color: #fff !important;
}
html[data-b2m-epaper="true"][data-bs-theme="light"] body .btn:not(.btn-link):not([class*="btn-outline-"]) svg,
html[data-b2m-epaper="true"][data-bs-theme="light"] body .btn:not(.btn-link):not([class*="btn-outline-"]) svg * {
  fill: currentColor !important;
}

""".strip()


def _render_bundle(name: str, sources: tuple[str, ...]) -> tuple[str, list[dict[str, str]]]:
    chunks: list[str] = [
        "/* Generated by app.frontend_assets. Do not edit this file directly. */\n"
    ]
    manifest: list[dict[str, str]] = []
    for relative in sources:
        source = STATIC_DIR / relative
        if not source.is_file():
            raise FileNotFoundError(f"Frontend bundle source is missing: {source}")
        content = source.read_text(encoding="utf-8")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        manifest.append({"path": relative, "sha256": digest})
        if name.endswith(".js"):
            chunks.append(f"\n/* ---- {relative} ---- */\n;\n{content.rstrip()}\n")
        else:
            chunks.append(f"\n/* ---- {relative} ---- */\n{content.rstrip()}\n")

    if name == "global-ui.css":
        # Legacy-compatible variables and the private v35 surface catalog are
        # generated from the same palette definitions. Live changes remain
        # synchronous and require no server roundtrip.
        live_css = build_theme_live_catalog_css()
        v35_surfaces = _build_v35_surface_catalog_css()
        complete_css = live_css + "\n" + v35_surfaces + "\n" + APPEARANCE_AUTHORITY_CSS
        chunks.append("\n/* ---- generated personal appearance v35 ---- */\n" + complete_css + "\n")
        manifest.append({"path": "<generated:appearance-v35>", "sha256": hashlib.sha256(complete_css.encode("utf-8")).hexdigest()})

    return "".join(chunks), manifest


def build_frontend_assets() -> dict[str, object]:
    """Build deterministic browser bundles from readable source layers."""
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    result: dict[str, object] = {"bundles": {}}

    for name, sources in BUNDLES.items():
        content, source_manifest = _render_bundle(name, sources)
        target = GENERATED_DIR / name
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, target)
        result["bundles"][name] = {
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "sources": source_manifest,
        }

    manifest = GENERATED_DIR / "manifest.json"
    manifest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def ensure_frontend_assets() -> None:
    """Build only when generated entrypoints are absent (mainly local source runs)."""
    if all((GENERATED_DIR / name).is_file() for name in BUNDLES):
        return
    build_frontend_assets()


if __name__ == "__main__":
    build_frontend_assets()
