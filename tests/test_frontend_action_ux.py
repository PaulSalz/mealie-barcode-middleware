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
    assert "action-v22-preset-settings" in source
    assert "Light entity ID" in source and "Timer duration (HH:MM:SS)" in source
    assert "Spoken message" in source and "Notification text" in source
    assert "trigger.json.entity_id | default" not in source
    assert "trigger.json.timer | default" not in source
    assert "validEntity(payload.timer, 'timer', 'timer.kitchen')" in source
    assert "const duration = /^\\d{1,3}:\\d{2}:\\d{2}$/.test(durationRaw)" in source
    assert "The target uses the fixed entity ID above" in source
    assert "These settings are available in both normal and Advanced mode." in source
    assert "relative_time if stats.last_execution else 'Never'" in template
    assert 'data-preset="notification"' in smoke
    assert 'window.__b2mCopiedText' in smoke




def test_home_assistant_scan_automation_uses_configured_webhook_and_includes_payload_fields():
    from app.services.homeassistant import build_scan_notification_automation, homeassistant_webhook_id

    url = "http://homeassistant.local:8123/api/webhook/b2m_scan_test"
    assert homeassistant_webhook_id(url) == "b2m_scan_test"
    assert homeassistant_webhook_id("http://homeassistant.local/not-a-webhook") is None
    automation = build_scan_notification_automation(url)
    assert "webhook_id: 'b2m_scan_test'" in automation
    assert "persistent_notification.create" in automation
    assert "{% set scan = ((trigger | default({})).json | default({})) %}" in automation
    for field in ("barcode", "item", "result_type", "action_url", "added_to_list", "paused", "quantity", "via", "needs_action", "brand", "item_source", "barcode_state", "barcode_known", "barcode_linked", "barcode_pending"):
        assert "scan.get('" + field + "'" in automation
    assert "Full payload" not in automation
    assert "processing" in automation
    assert "trigger.json.get(" not in automation
    assert "YOUR_WEBHOOK_ID" not in automation
    assert "target:" not in automation


def test_lookup_settings_show_api_urls_and_never_render_an_invalid_choice_as_blank():
    template = read("app/templates/settings.html")
    router = read("app/routers/settings.py")
    config = read("app/config.py")

    assert 'data-api-url="{{ item.field }}"' in template
    assert "valid_values = [" in router
    assert 'val = valid_values[0] if valid_values else ""' in router
    assert 'env_default = valid_values[0] if valid_values else ""' in router
    assert '"lookup_strategy": {' in config and '"type": "choice"' in config
    assert '"lookup_primary": {' in config and '"type": "choice"' in config


def test_matching_settings_are_not_hidden_behind_advanced_mode():
    source = read("app/static/js/settings-page.js")
    advanced_fields = source.split("var advancedFields = [", 1)[1].split("];", 1)[0]

    for field in (
        "fuzzy_match_threshold",
        "fuzzy_ambiguity_gap",
        "item_sync_interval_hours",
        "lookup_ttl_days",
        "max_retry_attempts",
    ):
        assert field not in advanced_fields


def test_system_settings_are_not_hidden_behind_advanced_mode():
    source = read("app/static/js/settings-page.js")
    advanced_fields = source.split("var advancedFields = [", 1)[1].split("];", 1)[0]

    for field in (
        "dashboard_poll_interval_seconds",
        "health_poll_interval_seconds",
        "shopping_print_poll_interval_seconds",
        "log_level",
    ):
        assert field not in advanced_fields


def test_recipe_target_routing_and_lists_are_set_in_current_targets():
    template = read("app/templates/barcode_detail.html")
    recipe_form = template.split('<form id="recipe-map-form"', 1)[1].split("</form>", 1)[0]

    assert "set its route and shopping lists in Current targets above" in template
    assert "route_select" not in recipe_form
    assert "shopping_list_ids" not in recipe_form


def test_appearance_bfcache_pages_reload_after_a_saved_theme_revision():
    source = read("app/static/js/theme-controls-v32.js")
    router = read("app/routers/access_v23.py")

    assert "b2m-appearance-revision-v2" in source
    assert "currentRevision === pageAppearanceRevision" in source
    assert "if (!event.persisted) return" not in source
    assert '"Cache-Control": "no-store, max-age=0"' in router


def test_homeassistant_notification_receives_all_scan_response_fields(monkeypatch):
    from types import SimpleNamespace
    from app.services import homeassistant

    captured = {}
    class Response:
        status_code = 200
        text = ""

    def post(url, json, timeout):
        captured.update(url=url, json=json, timeout=timeout)
        return Response()

    monkeypatch.setattr(homeassistant, "settings", SimpleNamespace(ha_webhook_url="http://ha/api/webhook/b2m"))
    monkeypatch.setattr(homeassistant, "_http", SimpleNamespace(post=post))
    details = {
        "result": "added_as_note",
        "via": "note",
        "needs_action": True,
        "brand": "Sample Brand",
        "quantity": "2",
        "item_source": "lookup",
    }
    homeassistant.notify_scan("123456", "Sample item", "added_as_note", "http://b2m/barcodes/123456", True, False, details)

    assert captured["json"]["barcode"] == "123456"
    assert captured["json"]["item"] == "Sample item"
    assert captured["json"]["via"] == "note"
    assert captured["json"]["needs_action"] is True
    assert captured["json"]["brand"] == "Sample Brand"
    assert captured["json"]["quantity"] == "2"
    assert captured["json"]["item_source"] == "lookup"


def test_mobile_dashboard_shows_recent_scans_and_remaining_cards():
    css = read("app/static/css/app.css")
    dashboard = read("app/templates/dashboard.html")
    template = read("app/templates/settings.html")
    hidden_cards_rule = ".b2m-dashboard-overview,\n  .b2m-dashboard-counts,\n  .b2m-dashboard-shopping,\n  .b2m-dashboard-frequent {\n    display: none !important;"
    assert hidden_cards_rule not in css
    assert ".b2m-dashboard-overview { order: 2; }" in css
    assert ".b2m-dashboard-counts { order: 3; }" in css
    assert ".b2m-dashboard-shopping { order: 4; }" in css
    assert ".b2m-dashboard-frequent { order: 5; }" in css
    assert ".b2m-dashboard-recent { order: 6; }" in css
    assert 'details class="card b2m-mobile-collapsible" open id="recent-scans-card"' in dashboard
    assert 'class="b2m-dashboard-frequent b2m-mobile-collapsible mb-3" open' in dashboard
    assert '<summary class="card-header b2m-mobile-collapse-summary d-md-none"><span class="card-title">Frequently used</span>' in dashboard
    assert ".b2m-dashboard-frequent-cards { margin: 0; padding: .55rem; }" in css
    assert ".b2m-dashboard-frequent .list-group-item { padding: .35rem .55rem; }" in css
    assert ".b2m-dashboard-mobile-flow {\n    display: flex;\n    flex-direction: column;\n    gap: .5rem;" in css
    assert ".b2m-dashboard-overview .card-body { padding: .65rem; }" in css
    assert ".b2m-stat-card .card-body {\n    min-height: unset;\n    padding: .6rem;" in css
    assert "#recent-scans-card #recent-scans-body tr {" in css and "padding: .35rem .45rem;" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    assert "@media (max-width: 359.98px)" in css
    assert "if (media.matches && recentScans) recentScans.open = false;" in read("app/static/js/dashboard-v2.js")
    for card in ("b2m-dashboard-overview", "b2m-dashboard-counts", "b2m-dashboard-shopping", "b2m-dashboard-frequent"):
        assert card in dashboard
    assert 'id="b2m-printer-connection-card"' in template
    assert 'class="card mb-3 d-none d-md-block" id="b2m-printer-connection-card"' not in template
    assert ".b2m-dashboard-counts .b2m-stat-card .h1" in css and "justify-content: space-between;" in css
    assert ".navbar {\n    position: sticky;" in css
    assert 'href="/profile/appearance"' in read("app/templates/base.html")
    assert 'data-field="barcode" data-label="Barcode"' in read("app/templates/barcodes.html")
    assert '#barcodes-table > tbody > tr:not(.barcodes-empty-row)' in css
    assert 'label-generator-layout' in read("app/templates/labels.html")
    assert 'shopping-print-layout' in read("app/templates/shopping_print.html")
    assert ".table.table-vcenter {\n    border-collapse: separate;\n    border-spacing: 0 .35rem;" in css
    assert ".table.table-vcenter > tbody > tr:not(.barcodes-empty-row)" in css
    assert ".label-page-header > .row > .col {\n    flex: 0 0 100%;" in css
    assert ".navbar-brand .ti-scan {\n    display: inline-flex;" in css
    assert "font-size: 1.5rem;" in css and ".navbar-brand .b2m-brand-text { font-size: 1rem;" in css
