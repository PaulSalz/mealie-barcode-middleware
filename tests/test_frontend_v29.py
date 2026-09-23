from pathlib import Path

from app.frontend_assets import GLOBAL_CSS, GLOBAL_JS


ROOT = Path(__file__).resolve().parents[1]


def test_v29_assets_are_bundled():
    assert "css/ui-v29.css" in GLOBAL_CSS
    assert "js/ui-v29.js" in GLOBAL_JS
    assert "js/shopping-fixes-v29.js" in GLOBAL_JS


def test_global_advanced_switch_is_persistent_and_reuses_legacy_controls():
    source = (ROOT / "app/static/js/ui-v29.js").read_text(encoding="utf-8")
    assert "advanced_settings" in source
    assert "b2m-global-advanced-toggle" in source
    assert "settings-show-advanced" in source
    assert "action-advanced-toggle" in source
    assert "/api/appearance-v24" in source


def test_radius_covers_selectgroup_and_normal_form_controls():
    source = (ROOT / "app/static/css/ui-v29.css").read_text(encoding="utf-8")
    assert ".form-control" in source
    assert ".form-select" in source
    assert ".form-selectgroup-label" in source
    assert '.form-selectgroup-input[name="theme_radius"]' not in source
    assert 'input[name="theme_radius"][value="2"] + .form-selectgroup-label' in source
    assert ".input-group-text" in source


def test_shopping_v29_has_header_connect_unit_hide_and_stable_local_mutations():
    source = (ROOT / "app/static/js/shopping-fixes-v29.js").read_text(encoding="utf-8")
    assert "shopping-print-connect-header" in source
    assert "shopping-print-override-hide-unit" in source
    assert "hide_unit" in source
    assert "/api/shopping-print/local-content" in source
    assert "window.location.reload()" in source


def test_shopping_receipt_settings_autosave_and_top_margin():
    source = (ROOT / "app/static/js/shopping-fixes-v29.js").read_text(encoding="utf-8")
    router = (ROOT / "app/routers/shopping_print.py").read_text(encoding="utf-8")
    assert "sp-top-margin" in source
    assert "top_margin_mm" in source
    assert "scheduleReceiptSettingsSave" in source
    assert "Saving automatically" in source
    assert "shopping-print-save-settings" in source
    assert "classList.add('d-none')" in source
    assert "_TOP_MARGIN_KEY" in router
    assert 'print_settings["top_margin_mm"]' in router


def test_shopping_router_canonicalizes_categories_and_supports_atomic_entry_routes():
    source = (ROOT / "app/routers/shopping_print.py").read_text(encoding="utf-8")
    assert "_normalize_payload_categories" in source
    assert "_canonicalize_local_entries" in source
    assert '"/api/shopping-print/local-content/add"' in source
    assert '"/api/shopping-print/local-content/delete"' in source
    assert "hide_unit" in source


def test_unit_hide_is_a_real_persisted_override():
    source = (ROOT / "app/services/shopping_print_overrides.py").read_text(encoding="utf-8")
    assert '"hide_unit": hide_unit' in source
    assert '_bool(override.get("hide_unit", False))' in source
    assert 'unit_display = ""' in source
