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
    rules.extend([
        'html[data-b2m-epaper="true"]{--b2m-v35-page-bg:#fff;--b2m-v35-surface-bg:var(--b2m-epaper-surface,#f7f7f7);--b2m-v35-surface-secondary:#fff;--b2m-v35-input-bg:#fff;--b2m-v35-text:#000;--b2m-v35-muted:var(--b2m-epaper-muted,#444);--b2m-v35-border:var(--b2m-epaper-border,#555);--b2m-v35-card-shadow:none}',
        'html[data-bs-theme="dark"][data-b2m-epaper="true"]{--b2m-v35-page-bg:#fff;--b2m-v35-surface-bg:var(--b2m-epaper-surface,#f7f7f7);--b2m-v35-surface-secondary:#fff;--b2m-v35-input-bg:#fff;--b2m-v35-text:#000;--b2m-v35-muted:var(--b2m-epaper-muted,#444);--b2m-v35-border:var(--b2m-epaper-border,#555);--b2m-v35-card-shadow:none}',
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
/* Theme switches update every surface in the same frame. */
html body, html body .page, html body .page-wrapper, html body .page-body,
html body .navbar, html body .card, html body .dropdown-menu,
html body .modal-content, html body .list-group-item,
html body .form-control, html body .form-select,
html body .form-selectgroup-label, html body .input-group-text {
  transition: none !important;
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
