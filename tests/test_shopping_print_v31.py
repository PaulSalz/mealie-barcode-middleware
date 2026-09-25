from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_canvas_observer_does_not_watch_style():
    source = read("app/static/js/shopping-fixes-v30.js")
    assert "attributeFilter:['width','height','data-height-mm']" in source
    assert "attributeFilter:['width','height','data-height-mm','style']" not in source


def test_canvas_observer_documents_feedback_loop_guard():
    source = read("app/static/js/shopping-fixes-v30.js")
    assert "MutationObserver microtask loop" in source
    assert "if (canvas.style.marginTop) canvas.style.marginTop = '';" in source


def test_hotfix_version():
    assert 'APP_VERSION = "2026.09.25.1"' in read("app/version.py")
