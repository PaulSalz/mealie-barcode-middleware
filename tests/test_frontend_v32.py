from pathlib import Path

from app.frontend_assets import GLOBAL_JS, LABEL_JS
from app.version import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v32_assets_replace_duplicate_theme_runtime():
    assert "js/theme-controls-v32.js" in GLOBAL_JS
    assert "js/ui-fixes-v30.js" not in GLOBAL_JS
    assert "js/labels-scope-v32.js" in LABEL_JS
    assert LABEL_JS.index("js/labels-scope-v32.js") < LABEL_JS.index("js/labels-fixes-v30.js")
    assert APP_VERSION == "2026.09.24.1"


def test_navbar_mode_uses_personal_theme_endpoint_and_captures_legacy_clicks():
    source = read("app/static/js/theme-controls-v32.js")
    router = read("app/routers/appearance_v24.py")
    assert "/api/appearance-v24/mode" in source
    assert "document.addEventListener('click'" in source
    assert "stopImmediatePropagation" in source
    assert "localStorage.setItem('theme-mode-override'" in source
    assert "__b2mThemeMutationVersion" in source
    assert '@router.post("/api/appearance-v24/mode")' in router
    assert "save_personal_theme" in router


def test_appearance_has_one_live_preview_controller():
    theme = read("app/static/js/theme-controls-v32.js")
    legacy = read("app/static/js/profile-live-v27.js")
    profile = read("app/static/js/profile-v23.js")
    assert "/api/appearance-v24/preview" in theme
    assert "requestAnimationFrame" in theme
    assert "AbortController" in theme
    assert "b2m-epaper-v9" in theme
    assert "data-bs-theme" in theme
    assert "window.__b2mThemeV32Loaded" in legacy
    assert "window.__b2mThemeV32Loaded" in profile


def test_theme_bootstrap_never_clears_personal_background_or_epaper_state():
    init = read("app/static/js/theme-init.js")
    templating = read("app/templating.py")
    assert "classList.remove('b2m-epaper" not in init
    assert "delete root.dataset.b2mBase" not in init
    assert "startedAtMutation" in init
    assert "get_template_theme" in templating
    assert "personal_theme(db, int(user_id))" in templating
    assert 'templates.env.globals["get_theme"] = get_template_theme' in templating


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
