import yaml

from app.routers.scan import ScanResponse, _barcode_resolution
from app.services.homeassistant import build_scan_notification_automation


def test_scan_automation_is_copyable_and_reports_barcode_state():
    automation = yaml.safe_load(
        build_scan_notification_automation("http://homeassistant.local/api/webhook/b2m_scan")
    )

    assert automation["alias"] == "B2M - Scan notification"
    assert automation["triggers"][0]["webhook_id"] == "b2m_scan"
    assert "processing" in automation["conditions"][0]["value_template"]
    notification = automation["actions"][0]["data"]
    assert "trigger | default({})" in notification["message"]
    for key in (
        "barcode_state",
        "barcode_known",
        "barcode_linked",
        "barcode_pending",
        "result_type",
        "action_url",
    ):
        assert key in notification["message"]
    assert "Full payload" not in notification["message"]


def test_barcode_resolution_distinguishes_linked_pending_and_unknown():
    assert _barcode_resolution(known=True, linked=True) == ("linked", True, True, False)
    assert _barcode_resolution(known=True, linked=False) == ("pending", True, False, True)
    assert _barcode_resolution(known=False, linked=False) == ("unknown", False, False, False)


def test_non_product_scan_states_are_distinct():
    assert ScanResponse(result="action_triggered", barcode_state="action").barcode_state == "action"
    assert ScanResponse(result="added", barcode_state="generic").barcode_state == "generic"
