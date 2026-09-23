from pathlib import Path

from app.frontend_assets import GLOBAL_JS, LABEL_JS
from app.version import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v30_assets_are_bundled_and_versioned():
    assert "js/ui-fixes-v30.js" in GLOBAL_JS
    # Shopping Print is being consolidated back to one controller in v31.
    # Keep the v30 source for regression/reference tests, but do not execute it.
    assert "js/shopping-fixes-v30.js" not in GLOBAL_JS
    assert "js/labels-fixes-v30.js" in LABEL_JS
    assert APP_VERSION == "2026.09.23.5"


def test_label_queue_uses_one_native_multipage_job():
    source = read("app/static/js/labels-fixes-v30.js")
    service = read("app/services/niimblue_batch_v30.py")
    router = read("app/routers/v30_fixes.py")
    assert "/labels/b21/print-batch-v30" in source
    assert "pages:pages" in source
    assert '"pages": clean_pages' in service
    assert '"/labels/b21/print-batch-v30"' in router
    assert "total_quantity * 20.0" in service


def test_small_label_text_is_fitted_and_clipped_consistently():
    source = read("app/static/js/labels-fixes-v30.js")
    assert "drawTextFit" in source
    assert "ctx.clip()" in source
    assert "height * .28" in source
    assert "height * .18" in source
    assert "el.scrollHeight > el.clientHeight" in source
    assert "physicalBounds" in source


def test_shopping_top_margin_modifies_real_preview_canvas():
    source = read("app/static/js/shopping-fixes-v30.js")
    assert "legacyTopMm" in source
    assert "desiredTopMm - legacyTopMm" in source
    assert "HTMLCanvasElement.prototype.toDataURL" in source
    assert "canvas.style.marginTop = ''" in source
    assert "canvas.dataset.heightMm = adjustedHeightMm" in source


def test_shopping_alias_drafts_quantity_hide_and_reset_are_covered():
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
    assert "save_category_aliases(db, list_id, {})" in router
    assert 'save_local_content(db, list_id, "", [])' in router


def test_secondary_shopping_connect_is_hidden():
    source = read("app/static/js/shopping-fixes-v30.js")
    assert "hideSecondaryConnect" in source
    assert "shopping-print-connect" in source
    assert "classList.add('d-none')" in source


def test_personal_theme_not_global_theme_drives_reload():
    source = read("app/static/js/theme-init.js")
    profile = read("app/templates/profile_appearance.html")
    live = read("app/static/js/ui-fixes-v30.js")
    assert "fetch('/api/appearance-v24'" in source
    assert "fetch('/api/theme'" not in source
    assert ">Background</label>" in profile
    assert "Neutral palette" not in profile
    assert "Radius changes only" in live
    assert "event.target.name === 'theme_radius'" in live
