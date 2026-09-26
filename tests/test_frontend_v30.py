from pathlib import Path

from app.frontend_assets import GLOBAL_JS, LABEL_JS
from app.version import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v30_assets_are_retained_without_legacy_theme_runtime():
    # v30 Shopping source remains for regression/reference; personal appearance
    # is owned by the single v35 controller.
    assert "js/ui-fixes-v30.js" not in GLOBAL_JS
    assert "js/shopping-fixes-v30.js" not in GLOBAL_JS
    assert "js/labels-fixes-v30.js" in LABEL_JS
    assert APP_VERSION == "2026.09.25.1"


def test_label_queue_uses_one_native_multipage_job():
    source = read("app/static/js/labels-fixes-v30.js")
    service = read("app/services/niimblue_batch_v30.py")
    router = read("app/routers/v30_fixes.py")
    assert "/labels/b21/jobs" in source
    assert "pages:pages" in source
    assert '"pages": clean_pages' in service
    assert '@router.post("/labels/b21/jobs", status_code=202)' in router
    assert '"/labels/b21/print-batch-v30"' in router  # legacy endpoint remains available
    assert "total_quantity * 30.0" in service
    assert "PrintOutcomeUnknown" in service


def test_settings_force_disconnect_is_always_available_on_desktop():
    template = read("app/templates/settings.html")
    client = read("app/static/js/settings-page.js")
    service = read("app/services/niimblue.py")
    assert 'id="b2m-printer-force-disconnect"' in template
    assert "d-none d-md-block" in template
    assert "method:'POST'" in client
    assert '_request("POST", "/disconnect", json={}, timeout=5)' in service
    assert "Disconnect requested" in service


def test_small_label_text_is_fitted_and_clipped_consistently():
    source = read("app/static/js/labels-fixes-v30.js")
    assert "drawTextFit" in source
    assert "ctx.clip()" in source
    assert "height * .28" in source
    assert "height * .18" in source
    assert "el.scrollHeight > el.clientHeight" in source
    assert "physicalBounds" in source


def test_shopping_top_margin_source_is_retained_for_regression_reference():
    source = read("app/static/js/shopping-fixes-v30.js")
    assert "legacyTopMm" in source
    assert "desiredTopMm - legacyTopMm" in source
    assert "HTMLCanvasElement.prototype.toDataURL" in source
    assert "canvas.style.marginTop = ''" in source
    assert "canvas.dataset.heightMm = adjustedHeightMm" in source


def test_shopping_alias_drafts_quantity_hide_and_reset_sources_are_retained():
    source = read("app/static/js/shopping-fixes-v30.js")
    overrides = read("app/services/shopping_print_overrides.py")
    router = read("app/routers/v30_fixes.py")
    assert "aliasDrafts" in source
    assert "restoreAliasDrafts" in source
    assert "shopping-print-override-hide-quantity" in source
    assert '"hide_quantity": hide_quantity' in overrides
    assert 'override.get("hide_quantity", False)' in overrides
    assert "/api/shopping-print/reset-list-v30" in source
    assert "save_category_order(db, list_id, [])" in router
    assert "save_category_aliases(db, list_id, [])" not in router
    assert "save_category_aliases(db, list_id, {})" in router
    assert 'save_local_content(db, list_id, "", [])' in router


def test_personal_theme_first_paint_has_no_async_reconciliation():
    source = read("app/static/js/theme-init.js")
    profile = read("app/templates/profile_appearance.html")
    assert "fetch(" not in source
    assert "--b2m-saved-mode" in source
    assert "--b2m-saved-base" in source
    assert "document.head.appendChild" not in source
    assert ">Background</label>" in profile
    assert ">Logo color</label>" in profile
    assert ">Button color</label>" in profile
    assert "Neutral palette" not in profile
