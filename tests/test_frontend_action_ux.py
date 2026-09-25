from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_item_shopping_destination_marks_the_dynamic_list_once_and_moves_edit_food_below_details():
    template = read("app/templates/item_detail.html")
    router = read("app/routers/items.py")

    assert "Dynamic — follow the current routing settings" in template
    assert "Use the automatically selected list" in template
    assert template.count('class="badge bg-blue text-blue-fg">Current default</span>') == 1
    assert " · default" not in template
    assert template.index("Details</h3>") < template.index("Scans by barcode") < template.index("Edit Food</h3>")
    assert '"default_shopping_list_name": default_shopping_list_name' in router


def test_action_examples_copy_ready_home_assistant_automations_without_advanced_json():
    source = read("app/static/js/action-v22.js")
    template = read("app/templates/action_detail.html")
    smoke = read("tools/ci_browser_smoke.py")

    assert "action: tts.speak" in source
    assert "action: light." in source
    assert "action: timer.start" in source
    assert "action: automation.trigger" in source
    assert "action: persistent_notification.create" in source
    assert "markAdvancedField(builder.querySelector('#action-v22-editor-accordion'))" in source
    assert "document.execCommand('copy')" in source
    assert "navigator.clipboard && typeof navigator.clipboard.writeText === 'function'" in source
    assert "Copy automation" in source
    assert "relative_time if stats.last_execution else 'Never'" in template
    assert 'data-preset="notification"' in smoke
    assert 'window.__b2mCopiedText' in smoke

