from pathlib import Path

from app.frontend_assets import GLOBAL_JS


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_legacy_shopping_v29_controller_is_not_executed():
    assert "js/shopping-fixes-v29.js" not in GLOBAL_JS
    assert "js/shopping-bootstrap-v31.js" in GLOBAL_JS
    assert GLOBAL_JS.index("js/shopping-bootstrap-v31.js") < GLOBAL_JS.index("js/shopping-fixes-v30.js")


def test_v31_redirects_only_shopping_bootstrap_and_preserves_autosave_controls():
    source = read("app/static/js/shopping-bootstrap-v31.js")
    assert "'/api/shopping-print/bootstrap'" in source
    assert "'/api/shopping-print/bootstrap-v31'" in source
    assert "shopping-print-connect-header" in source
    assert "shopping-print-override-hide-unit" in source
    assert "sp-top-margin" in source
    assert "Saving automatically" in source
    assert "settingsReady" in source


def test_fast_bootstrap_avoids_full_printer_status_diagnostics():
    router = read("app/routers/v30_fixes.py")
    assert '"/api/shopping-print/bootstrap-v31"' in router
    assert "niim_connected(timeout=0.8)" in router
    start = router.index("def shopping_print_bootstrap_v31")
    end = router.index('@router.post("/labels/b21/print-batch-v30")')
    body = router[start:end]
    assert "printer_status" not in body
    assert '"status_mode": "fast"' in body


def test_browser_smoke_exercises_shopping_print_and_bounds_list_requests():
    source = read("tools/ci_browser_smoke.py")
    assert 'page.goto(f"{BASE_URL}/shopping-print"' in source
    assert 'shopping_hits["legacy_bootstrap"] == 0' in source
    assert 'shopping_hits["lists"] <= 3' in source
    assert "Preview uses" in source
