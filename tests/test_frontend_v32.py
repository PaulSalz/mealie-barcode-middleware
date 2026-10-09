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
    assert APP_VERSION == "2026.10.09.2"


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


def test_label_print_buttons_replace_scope_picker_and_layer_inversion_is_available():
    editor = read("app/static/js/labels-b21-v2.js")
    queue = read("app/static/js/labels-page.js")
    layers = read("app/static/js/labels-v24.js")
    polish = read("app/static/js/labels-polish.js")
    assert "b21-v2-print-scope" not in editor and "b21-v2-copies" not in editor
    assert "async function submitPrintJob(entryId)" in editor
    assert "function printQueueEntry(entryId)" in queue
    assert 'class="btn btn-outline-primary entry-print"' in queue
    assert "Print all" in polish and "quickPrint.insertAdjacentElement('afterend', printAll)" in polish
    assert "toggleInvert" in editor and "data-layer-invert=" in layers
    assert "b21-layer-inverted" in editor
    assert "String(Math.round(Number(input.value)))" in editor



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
    queue = read("app/static/js/labels-page.js")
    assert 'id="b21-output-grid" data-active-mode="browser"' in output
    assert 'id="b21-printer-card"' in output
    assert "$('b21-printer-card')?.classList.toggle('d-none', browser)" in output
    assert 'header.className = \'b21-v2-header\'' in editor
    assert 'header.classList.toggle(\'d-none\', !b21Output || !b21Output.checked)' in editor
    assert '.b21-output-grid[data-active-mode="b21"] { grid-template-columns: minmax(0, 1fr) minmax(0, 2fr); }' in css
    assert "Preview label" not in output
    assert "entrySelect.hidden = true" in output
    assert "b21-preview-selector" not in output
    assert "selectQueueEntry: function (entryId)" in editor
    assert ".entry-edit" in queue
    assert "scrollIntoView({behavior:'smooth', block:'center'})" in queue


def test_b21_drag_and_resize_use_visible_objects_and_rotated_corners():
    editor = read("app/static/js/labels-b21-v2.js")
    resize = read("app/static/js/labels-b21-v2-patch.js")
    layers = read("app/static/js/labels-v24.js")
    css = read("app/static/css/labels-b21.css")
    assert "event.target.closest('.b21-code-content')" in editor
    assert "event.target.closest('.b21-v2-text-content')" in editor
    assert "localX=dx*Math.cos(angle)+dy*Math.sin(angle)" in editor
    assert "Math.min(originalWidthMm,originalHeightMm)+localX+localY" in resize
    assert "activeBox.offsetWidth||active.offsetWidth" in resize
    assert "editor.setCodeDimensions(Number(w.value),Number(h.value))" in resize
    assert "function currentCodeKind(image)" in resize
    assert "value.length<=32?'code128':'qr'" in resize
    assert "cx+cos*width/2-sin*height/2" in resize
    assert "window.__b2mPositionB21ResizeHandle" in layers
    assert "#b21-label-stage .b21-element { pointer-events: none; cursor: default; }" in css
    assert "#b21-label-stage .b21-code-content" in css
    assert "cursor: grab;" in css
    assert "const halfX=(Math.abs(widthMm*Math.cos(angle))+Math.abs(heightMm*Math.sin(angle)))/2/profile.width_mm*100" in editor
    assert "const halfY=(Math.abs(widthMm*Math.sin(angle))+Math.abs(heightMm*Math.cos(angle)))/2/profile.height_mm*100" in editor
    assert "type=\"button\" class=\"btn btn-outline-secondary\" data-align=" in editor
    assert "target.w=Math.max(2,Math.min(100,origW+2*localX/p.width_mm*100))" in editor
    assert "saveEntryStates();" in editor
    assert "positionTextResizeHandle" not in editor
    assert "el.id===selectedElementId&&(el.type==='line'||el.type==='frame')" in editor


def test_b21_qr_links_dimensions_and_code128_can_stretch():
    editor = read("app/static/js/labels-b21-v2.js")
    resize = read("app/static/js/labels-b21-v2-patch.js")
    queue = read("app/static/js/labels-page.js")
    css = read("app/static/css/labels-b21.css")
    assert "code.w=nextW;code.h=nextH" in editor
    assert "const sideMm=changedKey==='w'?Number(el.w||0)*p.width_mm/100:Number(el.h||0)*p.height_mm/100" in editor
    assert "el.w=sideMm/p.width_mm*100" in editor and "el.h=sideMm/p.height_mm*100" in editor
    assert "visual.style.width='100%'" in editor
    assert "image.style.objectFit='fill'" in editor
    assert "ctx.drawImage(img,-w/2,-h/2,w,h)" in editor
    assert "newWidthMm=Math.max(Math.min(2,dimensions.width)" in resize
    assert "newHeightMm=Math.max(Math.min(1,dimensions.height)" in resize
    assert "class=\"form-control entry-qty\" type=\"number\"" in queue
    assert "class=\"btn btn-outline-primary entry-print\"" in queue
    assert "class=\"btn btn-outline-primary entry-edit\"" in queue
    assert "entry-target-badge" not in queue and "kindLabel" not in queue
    assert "target.matches&&target.matches('.b21-v2-range')" in editor
    assert "document.querySelectorAll('.b21-v2-range:not(.d-none)').forEach((input)=>{const key=input.dataset.key;if(key in el" not in editor
    assert "#label-queue .entry-kind," in css
    assert "#b21-v2-copies" not in css
    assert "#label-queue .label-copy-actions .entry-print" in css


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


def test_b21_frame_is_a_layer_with_line_style_inversion_and_correct_handles():
    editor = read("app/static/js/labels-b21-v2.js")
    layers = read("app/static/js/labels-v24.js")
    css = read("app/static/css/labels-b21.css")
    assert "id:'frame',type:'frame'" in editor
    assert "state.elements.unshift(defaultFrame" in editor
    assert "b21-v2-line-style" in editor
    assert "el.type==='line'||el.type==='frame'" in editor
    assert "ctx.setLineDash" in editor
    assert "data-layer-invert=" in layers and "toggleInvert" in layers
    assert "element.type==='frame'?'border-outer'" in layers
    assert "b21-v2-frame-stroke" in css
    assert "b21-v2-frame-resize-handle" in css and "left: calc(100% + var(--b21-frame-width, 1px))" in css
    assert "b21-v2-line-resize-handle { left: 100%; top: 50%;" in css
    assert "positionTextResizeHandle" not in editor
    assert "el.id===selectedElementId&&(el.type==='line'||el.type==='frame')" in editor
    assert "setCodeDimensions: function" in editor
    assert "node.style.setProperty('--b21-frame-style',lineBorderStyle(el.lineStyle))" in editor
    assert "stroke.setAttribute('stroke-opacity','0')" in editor
    assert "el.type==='frame'||(key!=='h'||el.type!=='line')" in editor
    assert "[0,ctx.lineWidth*2]" in editor
    assert ".b21-v2-frame-stroke.b21-v2-element-selected" not in css
    assert "border-color: var(--b21-frame-color, #111) !important" in css
    assert "#b21-label-stage .b21-element.b21-v2-frame-selected" in css
    assert "outline: 1px solid var(--tblr-primary)" in css
    assert "outline-offset: calc(0px - var(--b21-frame-width, 1px))" in css
    assert ".b21-v2-frame-selected::after" not in css
    assert "cornerRadiusMm:0" in editor
    assert "rangeHtml('Corner radius','cornerRadiusMm',0,10,.5)" in editor
    assert "function traceRoundedRect(ctx,x,y,w,h,r)" in editor
    assert "state.frameInsetMm=1;state.frameWidthMm=.35" in editor
    assert "const el=state.elements.find((row)=>row.id===selectedElementId); if(!el)return;" in editor


def test_b21_connect_button_shares_the_output_choice_row_and_print_all_is_shared():
    b21 = read("app/static/js/labels-b21.js")
    editor = read("app/static/js/labels-b21-v2.js")
    polish = read("app/static/js/labels-polish.js")
    radio = b21.index('id="b21-output-b21"')
    head_start = b21.rfind('<div class="b21-output-choice-head">', 0, radio)
    printer = b21.index('id="b21-printer-card"', radio)
    head_end = b21.index('\n                        </div>\n                    </div>', printer)
    assert head_start < radio < printer < head_end
    assert "id='label-print'" in editor or "installPrintAllButton" in editor
    assert "Print all" in polish and "quickPrint.insertAdjacentElement('afterend', printAll)" in polish
