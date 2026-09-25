from pathlib import Path

from app.frontend_assets import GLOBAL_JS, LABEL_JS
from app.version import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v35_assets_keep_one_theme_runtime():
    assert "js/theme-controls-v32.js" in GLOBAL_JS
    assert "js/theme-preview-compat-v34.js" not in GLOBAL_JS
    assert "js/ui-fixes-v30.js" not in GLOBAL_JS
    assert "js/labels-scope-v32.js" in LABEL_JS
    assert LABEL_JS.index("js/labels-scope-v32.js") < LABEL_JS.index("js/labels-fixes-v30.js")
    assert APP_VERSION == "2026.09.24.3"


def test_navbar_mode_is_atomic_and_persisted_per_user():
    source = read("app/static/js/theme-controls-v32.js")
    router = read("app/routers/appearance_v24.py")
    assert "/api/appearance-v24/mode" in source
    assert "document.addEventListener('click'" in source
    assert "stopImmediatePropagation" in source
    assert "root.setAttribute('data-bs-theme', mode)" in source
    assert '@router.post("/api/appearance-v24/mode")' in router
    assert "save_personal_theme" in router
    assert "localStorage.setItem('theme-mode-override'" not in source


def test_live_appearance_is_synchronous_and_has_no_preview_roundtrip():
    source = read("app/static/js/theme-controls-v32.js")
    assets = read("app/frontend_assets.py")
    assert "data-b2m-base" not in source  # dataset API writes camelCase below
    assert "root.dataset.b2mBase" in source
    assert "root.dataset.b2mButtonColor" in source
    assert "root.dataset.b2mLogoColor" in source
    assert "root.dataset.b2mRadius" in source
    assert "root.dataset.b2mEpaper" in source
    assert "--b2m-epaper-border" in source
    assert "/api/appearance-v24/preview" not in source
    assert "AbortController" not in source
    assert "requestAnimationFrame" not in source
    assert "build_theme_live_catalog_css" in assets


def test_first_paint_is_server_theme_only():
    init = read("app/static/js/theme-init.js")
    templating = read("app/templating.py")
    assert "fetch(" not in init
    assert "localStorage.setItem" not in init
    assert "--b2m-saved-mode" in init
    assert "--b2m-saved-base" in init
    assert "document.head.appendChild" not in init
    assert "get_template_theme" in templating
    assert "personal_theme(db, int(user_id))" in templating
    assert 'templates.env.globals["get_theme"] = get_template_theme' in templating


def test_layer_order_uses_canonical_editor_state_without_duplicate_visibility():
    layers = read("app/static/js/labels-v24.js")
    editor = read("app/static/js/labels-b21-v2.js")
    assert "editor.moveLayer(id,direction)" in layers
    assert "data-layer-forward" in layers
    assert "data-layer-back" in layers
    assert "data-layer-visible" not in layers
    assert "b21-v2-visible" not in layers
    assert "b21-v2-visible" in editor
    assert "oldSection.classList.add('d-none')" in layers


def test_label_text_color_and_frame_controls_are_explicit():
    source = read("app/static/js/labels-v22.js")
    assert 'id="b21-v22-text-color"' in source
    assert '<option value="black">Black</option><option value="white">White</option>' in source
    assert "style.invert ? '#000' : 'transparent'" in source
    assert "style.invert ? '#fff' : '#111'" in source
    assert "Useful for cutting/alignment" not in source


def test_current_print_scope_bypasses_v30_queue_capture():
    source = read("app/static/js/labels-scope-v32.js")
    assert "b21-v2-print-scope" in source
    assert "currentScope() !== 'current'" in source
    assert "label-niim-print-current-v32" in source
    assert "button.id = 'label-niim-print'" in source
