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
    assert APP_VERSION == "2026.10.09.1"


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
    assert "data-layer-visible" in layers
    assert "setVisibility" in editor
    assert "entryStates = loadJson(ENTRY_KEY, entryStates)" in editor
    assert "b21-v2-visible" not in layers
    assert "b21-v2-visible" not in editor
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



def test_theme_back_navigation_and_mobile_settings_are_updated():
    theme = read("app/static/js/theme-controls-v32.js")
    css = read("app/static/css/app.css")
    settings = read("app/templates/settings.html")
    assert "appearanceRevisionKey" in theme
    assert "window.addEventListener('pageshow'" in theme
    assert "currentRevision === pageAppearanceRevision" in theme
    assert "if (!event.persisted) return;" not in theme
    assert "keepalive: true" in theme
    assert ".navbar > .container-xl > .navbar-brand" in css
    assert ".navbar > .container-xl > .navbar-toggler" in css
    assert "b2m-mobile-nav-divider" in css
    assert 'id="b2m-printer-force-disconnect"' in settings
    assert 'class="card mb-3 d-none d-md-block" id="b2m-printer-connection-card"' not in settings



def test_barcode_lookup_urls_and_strategy_are_visible_without_advanced_mode():
    settings = read("app/static/js/settings-page.js")
    config = read("app/config.py")
    assert "'lookup_primary', 'lookup_strategy'" not in settings
    assert "if (label.textContent.trim().replace(/\\s+/g, ' ') !== 'API endpoint') return;" not in settings
    assert '("failover", "Fail over to the other source")' in config
    assert '("complement", "Fill missing fields from the other source")' in config


def test_generated_ha_settings_automation_has_a_copyable_textarea():
    template = read("app/templates/settings.html")
    router = read("app/routers/settings.py")
    client = read("app/static/js/settings-page.js")
    assert 'id="homeassistant-scan-automation"' in template
    assert 'id="ha-scan-automation-yaml"' in template
    assert "build_scan_notification_automation(settings.ha_webhook_url)" in router
    assert "copy-ha-scan-automation" in client



def test_printer_settings_keep_disconnect_visible_and_explain_connectivity():
    source = read("app/static/js/ui-v9.js")
    assert 'id="v9-printer-disconnect"' in source
    assert "runConnectionAction('/labels/b21/disconnect'" in source
    assert "host-or-ip:5000" in source
    assert "status.service_reachable === false" in source



def test_printer_configuration_can_scan_and_select_a_device():
    source = read("app/static/js/ui-v9.js")
    router = read("app/routers/label_printer.py")
    service = read("app/services/niimblue.py")
    assert 'id="v9-printer-scan"' in source
    assert "'/labels/b21/scan'" in source
    assert "JSON.stringify({address})" in source
    assert '@router.post(\"/labels/b21/scan\")' in router
    scan_route = router.split('@router.post("/labels/b21/scan")', 1)[1].split('@router.post("/labels/b21/connect")', 1)[0]
    assert "_save_state(db, _CONNECTION_DESIRED_KEY, False)" in scan_route
    assert '"/scan"' in service


def test_printer_page_uses_one_connection_poll_and_pauses_for_scanning():
    source = read("app/static/js/ui-v9.js")
    settings = read("app/static/js/settings-page.js")
    assert "json('/labels/b21/status'" in source
    assert "printerScanInProgress" in source
    assert "get('tab') === 'printer') return" in settings


def test_b21_output_controls_follow_the_selected_output():
    output = read("app/static/js/labels-b21.js")
    editor = read("app/static/js/labels-b21-v2.js")
    css = read("app/static/css/labels-b21.css")
    assert 'id="b21-output-grid" data-active-mode="browser"' in output
    assert 'id="b21-printer-card"' in output
    assert "$('b21-printer-card')?.classList.toggle('d-none', browser)" in output
    assert 'header.className = \'b21-v2-header\'' in editor
    assert 'header.classList.toggle(\'d-none\', !b21Output || !b21Output.checked)' in editor
    assert '.b21-output-grid[data-active-mode="b21"] { grid-template-columns: minmax(0, 1fr) minmax(0, 2fr); }' in css
    assert '#b21-preview-selector { align-items: center; justify-content: flex-end; text-align: right; }' in css


def test_b21_drag_and_resize_use_visible_objects_and_rotated_corners():
    editor = read("app/static/js/labels-b21-v2.js")
    resize = read("app/static/js/labels-b21-v2-patch.js")
    layers = read("app/static/js/labels-v24.js")
    css = read("app/static/css/labels-b21.css")
    assert "event.target.closest('.b21-code-content')" in editor
    assert "event.target.closest('.b21-v2-text-content')" in editor
    assert "localX=dx*Math.cos(angle)+dy*Math.sin(angle)" in editor
    assert "projected=2*(localX+localY/aspect)/(1+1/(aspect*aspect))" in resize
    assert "function currentCodeKind(image)" in resize
    assert "value.length<=32?'code128':'qr'" in resize
    assert "cx+cos*width/2-sin*height/2" in resize
    assert "window.__b2mPositionB21ResizeHandle" in layers
    assert "#b21-label-stage .b21-element { pointer-events: none; cursor: default; }" in css
    assert "#b21-label-stage .b21-code-content" in css
    assert "cursor: grab;" in css
    assert "elementWidthMm=Math.min(elementWidthMm,elementHeightMm*ratio)" in editor
    assert "positionTextResizeHandle(node,handle)" in editor


def test_b21_presets_reset_button_and_queue_feedback_regressions():
    editor = read("app/static/js/labels-b21-v2.js")
    presets = read("app/static/js/ui-v13-fixes.js")
    css = read("app/static/css/labels-b21.css")
    queue = read("app/static/js/labels-polish.js")
    assert 'id="b21-v2-content-actions"><button' in editor
    assert 'id="b21-v2-reset-element"' in editor
    assert 'id="b21-v2-delete-element"' in editor
    assert "clearPresetActive();" in presets
    assert "event.target.closest('#b21-v2-reset-all')" in presets
    assert "var(--tblr-primary)" in css
    assert "showQueueFeedback('Updated');" in queue
    assert "Updated · " not in queue
