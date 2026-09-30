import yaml

from app.services.homeassistant import build_scan_notification_automation


def test_scan_notification_message_preserves_sections_and_line_breaks():
    automation = yaml.safe_load(build_scan_notification_automation(None))
    message = automation["actions"][0]["data"]["message"]

    assert "**Barcode & Artikel**\n- Barcode:" in message
    assert "\n\n**Verknüpfung**\n" in message
    assert "\n\n**Scan-Ergebnis**\n" in message
    assert "\n\n**Artikeldetails**\n" in message
    assert "\n\n**System**\n" in message
    assert "- Link: {{ scan.get('action_url', '—') }}" in message
