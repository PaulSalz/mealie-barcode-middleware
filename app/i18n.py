from __future__ import annotations

from jinja2 import pass_context
from sqlalchemy.orm import Session

from app.models import SystemState

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = {"en": "English", "de": "Deutsch"}
_KEY_PREFIX = "ui.language."

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "nav.dashboard": "Dashboard", "nav.barcodes": "Barcodes", "nav.items": "Items",
        "nav.actions": "Actions", "nav.labels": "Labels", "nav.activity": "Activity",
        "nav.documentation": "Documentation", "nav.settings": "Settings", "nav.logout": "Logout",
        "common.cancel": "Cancel", "common.delete": "Delete", "common.save": "Save",
        "common.retry": "Retry", "common.ready": "Ready", "common.needs_attention": "Needs attention",
        "language.title": "Language", "language.english": "English", "language.german": "German",
        "dashboard.shopping_lists": "Shopping lists", "dashboard.print_list": "Print shopping list",
        "dashboard.recent_scans": "Recent Scans", "dashboard.connected": "Connected",
        "dashboard.unreachable": "Unreachable",
        "onboarding.title": "Get B2M ready for scanning", "onboarding.first_setup": "First setup",
        "onboarding.intro": "Work through these checks once. You can leave this page at any time and come back later.",
        "onboarding.progress": "ready", "onboarding.finish": "Finish setup",
        "onboarding.continue": "Continue to dashboard", "onboarding.recheck": "Recheck",
        "onboarding.mealie": "Mealie connection",
        "onboarding.mealie_ok": "B2M can reach Mealie and authenticate with the configured API key.",
        "onboarding.mealie_todo": "B2M cannot reach Mealie yet. Check the URL/API key in your deployment and use the connection test.",
        "onboarding.mealie_action": "Check Mealie settings",
        "onboarding.list": "Shopping list", "onboarding.list_ok": "A default shopping list is selected.",
        "onboarding.list_todo": "Choose which Mealie shopping list B2M should use when a barcode does not specify one.",
        "onboarding.list_action": "Choose shopping list",
        "onboarding.token": "Scanner access", "onboarding.token_ok": "At least one scanner token exists.",
        "onboarding.token_todo": "Create a scanner token so the USB bridge, phone app, or another scanner can authenticate.",
        "onboarding.token_action": "Create scanner token",
        "onboarding.scanner": "Scanner online", "onboarding.scanner_ok": "A scanner is connected and reporting to B2M.",
        "onboarding.scanner_todo": "Start your scanner bridge or scanner app. This check turns green automatically after it reports in.",
        "onboarding.scanner_action": "Open scanner setup",
        "onboarding.scan": "First scan", "onboarding.scan_ok": "B2M has received at least one real scan.",
        "onboarding.scan_todo": "Scan any barcode. Unknown products are fine — the goal is only to verify the complete path.",
        "onboarding.scan_action": "View barcodes",
        "onboarding.all_ready": "Everything is ready",
        "onboarding.all_ready_text": "B2M can now be used normally. The dashboard will continue to show connection problems if anything goes offline later.",
        "onboarding.later": "You can finish later",
        "onboarding.later_text": "Nothing here locks the application. Finish setup now or continue to the dashboard and return when convenient.",
    },
    "de": {
        "nav.dashboard": "Übersicht", "nav.barcodes": "Barcodes", "nav.items": "Artikel",
        "nav.actions": "Aktionen", "nav.labels": "Etiketten", "nav.activity": "Aktivität",
        "nav.documentation": "Dokumentation", "nav.settings": "Einstellungen", "nav.logout": "Abmelden",
        "common.cancel": "Abbrechen", "common.delete": "Löschen", "common.save": "Speichern",
        "common.retry": "Erneut versuchen", "common.ready": "Bereit", "common.needs_attention": "Handlung nötig",
        "language.title": "Sprache", "language.english": "Englisch", "language.german": "Deutsch",
        "dashboard.shopping_lists": "Einkaufslisten", "dashboard.print_list": "Einkaufsliste drucken",
        "dashboard.recent_scans": "Letzte Scans", "dashboard.connected": "Verbunden",
        "dashboard.unreachable": "Nicht erreichbar",
        "onboarding.title": "B2M zum Scannen einrichten", "onboarding.first_setup": "Ersteinrichtung",
        "onboarding.intro": "Diese Prüfungen müssen nur einmal durchlaufen werden. Du kannst die Seite jederzeit verlassen und später zurückkommen.",
        "onboarding.progress": "bereit", "onboarding.finish": "Einrichtung abschließen",
        "onboarding.continue": "Zur Übersicht", "onboarding.recheck": "Erneut prüfen",
        "onboarding.mealie": "Mealie-Verbindung",
        "onboarding.mealie_ok": "B2M kann Mealie erreichen und sich mit dem konfigurierten API-Schlüssel anmelden.",
        "onboarding.mealie_todo": "B2M kann Mealie noch nicht erreichen. Prüfe URL und API-Schlüssel der Installation und führe den Verbindungstest aus.",
        "onboarding.mealie_action": "Mealie-Einstellungen prüfen",
        "onboarding.list": "Einkaufsliste", "onboarding.list_ok": "Eine Standard-Einkaufsliste ist ausgewählt.",
        "onboarding.list_todo": "Wähle aus, welche Mealie-Einkaufsliste B2M verwenden soll, wenn ein Barcode keine Liste vorgibt.",
        "onboarding.list_action": "Einkaufsliste wählen",
        "onboarding.token": "Scanner-Zugriff", "onboarding.token_ok": "Mindestens ein Scanner-Token ist vorhanden.",
        "onboarding.token_todo": "Erstelle einen Scanner-Token, damit USB-Bridge, Handy-App oder andere Scanner sich anmelden können.",
        "onboarding.token_action": "Scanner-Token erstellen",
        "onboarding.scanner": "Scanner online", "onboarding.scanner_ok": "Ein Scanner ist verbunden und meldet sich bei B2M.",
        "onboarding.scanner_todo": "Starte die Scanner-Bridge oder Scanner-App. Der Status wird automatisch grün, sobald sie sich meldet.",
        "onboarding.scanner_action": "Scanner-Einrichtung öffnen",
        "onboarding.scan": "Erster Scan", "onboarding.scan_ok": "B2M hat mindestens einen echten Scan empfangen.",
        "onboarding.scan_todo": "Scanne einen beliebigen Barcode. Unbekannte Produkte sind in Ordnung — hier wird nur der komplette Datenweg geprüft.",
        "onboarding.scan_action": "Barcodes anzeigen",
        "onboarding.all_ready": "Alles ist bereit",
        "onboarding.all_ready_text": "B2M kann jetzt normal verwendet werden. Die Übersicht zeigt weiterhin an, falls später eine Verbindung ausfällt.",
        "onboarding.later": "Du kannst später weitermachen",
        "onboarding.later_text": "Die Einrichtung sperrt die Anwendung nicht. Du kannst jetzt zur Übersicht wechseln und später zurückkommen.",
    },
}


def normalize_language(value: str | None) -> str:
    value = str(value or "").strip().lower().replace("_", "-")
    short = value.split("-", 1)[0]
    return short if short in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def language_for_user(db: Session, user_id: int | str | None, fallback: str = DEFAULT_LANGUAGE) -> str:
    if not user_id:
        return normalize_language(fallback)
    row = db.get(SystemState, f"{_KEY_PREFIX}{user_id}")
    return normalize_language(row.value if row and row.value else fallback)


def save_language(db: Session, user_id: int | str, language: str) -> str:
    language = normalize_language(language)
    key = f"{_KEY_PREFIX}{user_id}"
    row = db.get(SystemState, key)
    if row:
        row.value = language
    else:
        db.add(SystemState(key=key, value=language))
    db.commit()
    return language


def translate(language: str, key: str, default: str | None = None) -> str:
    language = normalize_language(language)
    return _TRANSLATIONS.get(language, {}).get(key) or _TRANSLATIONS[DEFAULT_LANGUAGE].get(key) or default or key


@pass_context
def template_translate(context, key: str, default: str | None = None) -> str:
    request = context.get("request")
    language = DEFAULT_LANGUAGE
    if request is not None:
        language = normalize_language(request.session.get("ui_language"))
    return translate(language, key, default)


@pass_context
def template_language(context) -> str:
    request = context.get("request")
    if request is None:
        return DEFAULT_LANGUAGE
    return normalize_language(request.session.get("ui_language"))
