from pathlib import Path

from app.theme import (
    COLOR_CSS,
    THEME_CHOICES,
    THEME_DEFAULTS,
    build_theme_css,
    build_theme_live_catalog_css,
    normalize_theme,
)


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_logo_and_button_colors_are_separate_domains():
    assert "rainbow" in THEME_CHOICES["logo_color"]
    assert "rainbow" not in THEME_CHOICES["button_color"]
    assert set(THEME_CHOICES["button_color"]) == set(COLOR_CSS)


def test_legacy_accent_migrates_without_allowing_rainbow_buttons():
    fixed = normalize_theme({"color": "teal"})
    assert fixed["logo_color"] == "teal"
    assert fixed["button_color"] == "teal"

    rainbow = normalize_theme({"color": "rainbow"})
    assert rainbow["logo_color"] == "rainbow"
    assert rainbow["button_color"] == THEME_DEFAULTS["button_color"]
    assert rainbow["color"] == rainbow["button_color"]


def test_personal_theme_does_not_inherit_legacy_global_theme():
    source = read("app/access_v23.py")
    personal = source.split("def personal_theme", 1)[1].split("def save_personal_theme", 1)[0]
    assert "get_theme(" not in personal
    assert "normalize_theme(THEME_DEFAULTS)" in personal
    assert "theme_key(int(user_id))" in personal


def test_persisted_theme_contains_complete_first_paint_state():
    css = build_theme_css({
        "mode": "dark",
        "logo_color": "rainbow",
        "button_color": "green",
        "base": "zinc",
        "radius": "1.5",
        "font": "serif",
        "epaper": "false",
        "contrast": "65",
        "date_style": "medium",
    })
    assert "--b2m-saved-mode:dark" in css
    assert "--tblr-border-radius:0.8rem" in css
    assert "--b2m-page-bg:#09090b" in css
    assert "--tblr-primary:#2fb344" in css
    assert "b2m-logo-rainbow" in css


def test_personal_stylesheet_exports_complete_saved_state_for_head_bootstrap():
    access = read("app/access_v23.py")
    init = read("app/static/js/theme-init.js")
    for key in ("mode", "base", "button-color", "logo-color", "radius", "font", "epaper", "contrast"):
        assert f'"{key}"' in access
        assert f"--b2m-saved-{key}" in init
    for dataset in ("b2mBase", "b2mButtonColor", "b2mLogoColor", "b2mRadius", "b2mFont", "b2mEpaper"):
        assert f"root.dataset.{dataset}" in init
    assert "fetch(" not in init


def test_live_catalog_controls_entire_page_synchronously():
    css = build_theme_live_catalog_css()
    for selector in (
        "body,.page,.page-wrapper,.page-body",
        ".navbar,.card,.dropdown-menu,.modal-content,.offcanvas,.toast,.list-group-item",
        ".form-control,.form-select,.input-group-text,.form-selectgroup-label",
        "html[data-bs-theme=dark][data-b2m-base=",
        "data-b2m-button-color",
        "data-b2m-logo-color",
        "data-b2m-radius",
        "data-b2m-epaper",
    ):
        assert selector in css
    assert 'a[href="/settings?tab=appearance"]{display:none!important}' in css


def test_live_controller_has_no_server_preview_or_async_theme_reconciliation():
    source = read("app/static/js/theme-controls-v32.js")
    init = read("app/static/js/theme-init.js")
    assert "/api/appearance-v24/preview" not in source
    assert "requestAnimationFrame" not in source
    assert "AbortController" not in source
    assert "fetch('/api/appearance-v24'," in source  # persistence only
    assert "root.dataset.b2mBase" in source
    assert "root.dataset.b2mButtonColor" in source
    assert "root.dataset.b2mLogoColor" in source
    assert "fetch(" not in init


def test_v35_initializes_before_legacy_layers_and_disables_their_theme_repairs():
    frontend = read("app/frontend_assets.py")
    bundle = frontend.split("GLOBAL_JS = (", 1)[1].split(")\nLABEL_JS", 1)[0]
    assert bundle.index('"js/theme-controls-v32.js"') < bundle.index('"js/ui-v24.js"')
    assert bundle.index('"js/theme-controls-v32.js"') < bundle.index('"js/regression-v28.js"')
    assert bundle.index('"js/theme-controls-v32.js"') < bundle.index('"js/ui-v29.js"')

    v24 = read("app/static/js/ui-v24.js")
    v28 = read("app/static/js/regression-v28.js")
    v29 = read("app/static/js/ui-v29.js")
    assert "appearanceV35" in v24 and "if(appearanceV35)return;" in v24
    assert "appearanceV35" in v28 and "if (appearanceV35) return;" in v28
    assert "appearanceV35" in v29 and "if (appearanceV35) return;" in v29
    assert "if (!appearanceV35 && data.theme)" in v29


def test_profile_form_uses_new_color_model_and_no_legacy_accent_control():
    profile = read("app/templates/profile_appearance.html")
    assert "Logo color" in profile
    assert "Button color" in profile
    assert 'name="theme_logo_color"' in profile
    assert 'name="theme_button_color"' in profile
    assert 'name="theme_color"' not in profile
    assert 'select name="theme_radius"' not in profile


def test_global_appearance_entrypoints_are_retired():
    guard = read("app/personal_appearance_guard.py")
    main = read("app/main.py")
    assert 'path == "/settings/theme"' in guard
    assert 'request.query_params.get("tab") == "appearance"' in guard
    assert 'RedirectResponse("/profile/appearance"' in guard
    assert "PersonalAppearanceOnlyMiddleware" in main


def test_legacy_ui_preferences_save_date_style_per_user():
    source = read("app/routers/appearance_v3.py")
    assert "save_personal_theme(db, user_id, {\"date_style\": date_style})" in source
    assert "save_theme(" not in source
    assert "set_cached_theme" not in source
