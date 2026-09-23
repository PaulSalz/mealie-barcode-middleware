from __future__ import annotations

from jinja2 import pass_context
from sqlalchemy.orm import Session

from app.models import SystemState

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = {"en": "English", "de": "Deutsch"}
_KEY_PREFIX = "ui.language."

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "nav.dashboard": "Dashboard",
        "nav.barcodes": "Barcodes",
        "nav.items": "Items",
        "nav.actions": "Actions",
        "nav.labels": "Labels",
        "nav.activity": "Activity",
        "nav.documentation": "Documentation",
        "nav.settings": "Settings",
        "nav.logout": "Logout",
        "common.cancel": "Cancel",
        "common.delete": "Delete",
        "common.save": "Save",
        "common.retry": "Retry",
        "common.ready": "Ready",
        "common.needs_attention": "Needs attention",
        "language.title": "Language",
        "language.english": "English",
        "language.german": "German",
        "dashboard.shopping_lists": "Shopping lists",
        "dashboard.print_list": "Print shopping list",
        "dashboard.recent_scans": "Recent Scans",
        "dashboard.connected": "Connected",
        "dashboard.unreachable": "Unreachable",
        "onboarding.title": "Get B2M ready for scanning",
        "onboarding.first_setup": "First setup",
        "onboarding.finish": "Finish setup",
        "onboarding.continue": "Continue to dashboard",
        "onboarding.recheck": "Recheck",
    },
    "de": {
        "nav.dashboard": "Übersicht",
        "nav.barcodes": "Barcodes",
        "nav.items": "Artikel",
        "nav.actions": "Aktionen",
        "nav.labels": "Etiketten",
        "nav.activity": "Aktivität",
        "nav.documentation": "Dokumentation",
        "nav.settings": "Einstellungen",
        "nav.logout": "Abmelden",
        "common.cancel": "Abbrechen",
        "common.delete": "Löschen",
        "common.save": "Speichern",
        "common.retry": "Erneut versuchen",
        "common.ready": "Bereit",
        "common.needs_attention": "Handlung nötig",
        "language.title": "Sprache",
        "language.english": "Englisch",
        "language.german": "Deutsch",
        "dashboard.shopping_lists": "Einkaufslisten",
        "dashboard.print_list": "Einkaufsliste drucken",
        "dashboard.recent_scans": "Letzte Scans",
        "dashboard.connected": "Verbunden",
        "dashboard.unreachable": "Nicht erreichbar",
        "onboarding.title": "B2M zum Scannen einrichten",
        "onboarding.first_setup": "Ersteinrichtung",
        "onboarding.finish": "Einrichtung abschließen",
        "onboarding.continue": "Zur Übersicht",
        "onboarding.recheck": "Erneut prüfen",
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
