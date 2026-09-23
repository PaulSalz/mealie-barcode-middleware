from pathlib import Path

from app.frontend_assets import GLOBAL_CSS, GLOBAL_JS, LABEL_JS


def test_b21_shell_is_loaded_before_editor_layers():
    assert "js/labels-b21.js" in LABEL_JS
    assert LABEL_JS.index("js/labels-b21.js") < LABEL_JS.index("js/labels-b21-v2.js")
    source = Path("app/static/js/labels-b21.js").read_text(encoding="utf-8")
    for required_id in (
        "b21-output-card",
        "b21-connection-bar",
        "b21-connect-button",
        "b21-profile-select",
        "b21-layout-body",
        "b21-label-stage",
    ):
        assert required_id in source


def test_regression_repair_assets_are_bundled():
    assert "js/regression-v28.js" in GLOBAL_JS
    assert "css/ui-v28.css" in GLOBAL_CSS
