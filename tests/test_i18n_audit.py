from __future__ import annotations

from app.i18n import translate


AUDIT_KEYS = (
    "base.pause_banner",
    "base.notifications",
    "base.confirm_title",
    "base.pause_title",
    "empty.actions_title",
    "empty.actions_text",
    "empty.barcodes_title",
    "empty.barcodes_filtered_title",
    "empty.items_title",
    "empty.items_filtered_title",
)


def test_audit_ui_strings_exist_in_both_languages():
    for key in AUDIT_KEYS:
        assert translate("en", key) != key
        assert translate("de", key) != key
