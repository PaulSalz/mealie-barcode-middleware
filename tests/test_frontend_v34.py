from pathlib import Path

from app.theme import THEME_DEFAULTS, build_theme_css, theme_runtime_config
from app.version import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v34_version_and_runtime_tokens():
    assert APP_VERSION == "2026.09.24.2"
    runtime = theme_runtime_config()
    assert runtime["defaults"] == THEME_DEFAULTS
    assert runtime["radius_rem"]["1"] == 0.5
    assert runtime["radius_rem"]["2"] == 1.1
    assert runtime["grays"]["slate"]["950"] == "#020617"


def test_default_radius_is_render_blocking_not_javascript_only():
    css = build_theme_css(dict(THEME_DEFAULTS))
    assert "--tblr-border-radius-scale:1" in css
    assert "--tblr-border-radius:0.5rem" in css
    assert "--tblr-border-radius-sm:0.36rem" in css
    assert "--tblr-border-radius-lg:0.725rem" in css
    assert "--tblr-border-radius-xl:0.95rem" in css


def test_background_palette_defines_complete_light_and_dark_surfaces():
    theme = dict(THEME_DEFAULTS)
    theme["base"] = "slate"
    css = build_theme_css(theme)
    assert "[data-bs-theme=light]" in css
    assert "--tblr-body-bg:#f1f5f9" in css
    assert "--tblr-bg-surface:#f8fafc" in css
    assert "[data-bs-theme=dark]" in css
    assert "--tblr-body-bg:#020617" in css
    assert "--tblr-bg-surface:#0f172a" in css
    assert "--tblr-border-color:#1e293b" in css


def test_epaper_css_is_complete_for_both_modes_and_contrast():
    theme = dict(THEME_DEFAULTS)
    theme.update({"epaper": "true", "contrast": "90", "base": "slate"})
    css = build_theme_css(theme)
    assert "html{filter:grayscale(1)}" in css
    assert "--tblr-body-bg:#fff" in css
    assert "--tblr-primary:#000" in css
    assert "--tblr-bg-surface-secondary:#fff" in css
    assert "--tblr-bg-surface-dark:#000" in css
    assert "--tblr-border-color:rgb(67,67,67)" in css
    assert ".navbar" in css
    assert ".card" in css


def test_first_paint_uses_server_theme_not_browser_cache():
    base = read("app/templates/base.html")
    assert 'data-bs-theme="{{ t.mode }}"' in base
    assert 'data-b2m-base="{{ t.base }}"' in base
    assert 'data-b2m-radius="{{ t.radius }}"' in base
    assert "theme-mode-override" not in base
    assert "theme-base-override" not in base
    assert "theme-epaper-override" not in base
    assert "theme-init.js" not in base
    assert "/user-theme.css" in base


def test_live_preview_is_complete_and_has_no_preview_network_dependency():
    source = read("app/static/js/theme-controls-v32.js")
    profile = read("app/templates/profile_appearance.html")
    assert "b2m-theme-runtime-config" in profile
    assert "function buildThemeCss(state)" in source
    assert "preview.textContent = buildThemeCss(state)" in source
    assert "persistedTheme.disabled = true" in source
    assert "/api/appearance-v24/preview" not in source
    assert "localStorage.setItem('theme-mode-override'" not in source
    assert "--tblr-bg-surface-secondary" in source
    assert "html{filter:grayscale(1)}" in source
