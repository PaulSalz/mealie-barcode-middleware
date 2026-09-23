from pathlib import Path

from app.frontend_assets import GLOBAL_JS, LABEL_JS
from app.version import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v33_theme_asset_replaces_duplicate_theme_runtime():
    assert "js/theme-controls-v33.js" in GLOBAL_JS
    assert "js/theme-controls-v32.js" not in GLOBAL_JS
    assert "js/ui-fixes-v30.js" not in GLOBAL_JS
    assert "js/labels-scope-v32.js" in LABEL_JS
    assert LABEL_JS.index("js/labels-scope-v32.js") < LABEL_JS.index("js/labels-fixes-v30.js")
    assert APP_VERSION == "2026.09.24.1"


def test_navbar_mode_uses_personal_theme_endpoint_and_live_state():
    source = read("app/static/js/theme-controls-v33.js")
    router = read("app/routers/appearance_v24.py")
    assert "/api/appearance-v24/mode" in source
    assert "stopImmediatePropagation" in source
    assert "localStorage.setItem('theme-mode-override'" in source
    assert '@router.post("/api/appearance-v24/mode")' in router
    assert "save_personal_theme" in router


def test_appearance_preview_is_synchronous_and_has_one_controller():
    theme = read("app/static/js/theme-controls-v33.js")
    legacy = read("app/static/js/profile-live-v27.js")
    profile = read("app/static/js/profile-v23.js")
    assert "/api/appearance-v24/preview" not in theme
    assert "buildThemeCss" in theme
    assert "renderProfilePreview" in theme
    assert "b2m-epaper-v9" in theme
    assert "data-bs-theme" in theme
    assert "window.__b2mThemeV32Loaded = true" in theme
    assert "window.__b2mThemeV32Loaded" in legacy
    assert "window.__b2mThemeV32Loaded" in profile


def test_theme_initialization_does_not_repaint_from_async_api():
    source = read("app/static/js/theme-init.js")
    assert "fetch(" not in source
    assert "/api/appearance-v24" not in source
    assert "classList.remove('b2m-epaper" not in source


def test_server_template_theme_is_request_aware():
    source = read("app/templating.py")
    assert "_effective_theme_for_request" in source
    assert "personal_theme(db, int(user_id))" in source
    assert 'templates.env.globals["get_theme"] = _template_theme' in source


def test_legacy_ui_v29_no_longer_writes_theme_palette():
    source = read("app/static/js/ui-v29.js")
    assert "applyPalette" not in source
    assert "--tblr-body-bg" not in source
    assert "theme_base" not in source


def test_layer_visibility_drives_canonical_editor_immediately():
    source = read("app/static/js/labels-v24.js")
    assert "b21-v2-visible" in source
    assert "input.dispatchEvent(new Event('change',{bubbles:true}))" in source
    assert "direct storage writes only become" in source
    assert "oldSection.classList.add('d-none')" in source


def test_current_print_scope_bypasses_v30_queue_capture():
    source = read("app/static/js/labels-scope-v32.js")
    assert "b21-v2-print-scope" in source
    assert "currentScope() !== 'current'" in source
    assert "label-niim-print-current-v32" in source
    assert "button.id = 'label-niim-print'" in source
