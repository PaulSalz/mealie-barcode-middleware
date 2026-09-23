import logging
from typing import Any

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    mealie_url: str
    mealie_api_key: str
    # Legacy fallback only. The runtime default is selected from Mealie in Settings.
    mealie_shopping_list_id: str = ""

    off_enabled: bool = True
    off_url_base: str = "https://world.openfoodfacts.org/api/v2/product/"
    upcdb_enabled: bool = False
    upcdb_url_base: str = "https://api.upcdatabase.org/product/"
    upcdb_api_key: str | None = None

    lookup_strategy: str = "failover"
    lookup_primary: str = "off"
    lookup_enrich_in_background: bool = True

    item_sync_interval_hours: int = 6
    fuzzy_match_threshold: int = 85
    fuzzy_ambiguity_gap: int = 10
    lookup_ttl_days: int = 30
    max_retry_attempts: int = 10

    unknown_barcode_action: str = "add_to_list"

    middleware_base_url: str = ""
    ha_webhook_url: str = ""
    ha_notification_mode: str = "unresolved"
    notification_toast_seconds: int = 12
    notification_group_window_seconds: int = 30

    # Browser-side polling. Event-driven scan refreshes still happen immediately;
    # these intervals only control the periodic safety-net syncs while a page is visible.
    dashboard_poll_interval_seconds: int = 5
    health_poll_interval_seconds: int = 5
    shopping_print_poll_interval_seconds: int = 5

    db_path: str = "/data/barcode.db"
    timezone: str = "Europe/Berlin"
    session_max_age_days: int = 7
    port: int = 8000
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


EDITABLE_SETTINGS: dict[str, dict[str, Any]] = {
    "off_enabled": {
        "type": "bool", "label": "OFF_ENABLED", "description": "Enabled",
        "help": "Community-maintained product database. Best coverage for EU grocery items.",
        "group": "Barcode Lookup Sources", "section": "Open Food Facts",
    },
    "upcdb_enabled": {
        "type": "bool", "label": "UPCDB_ENABLED", "description": "Enabled",
        "help": "Commercial API (requires API key). Better coverage for US products.",
        "group": "Barcode Lookup Sources", "section": "UPC Database",
    },
    "lookup_primary": {
        "type": "choice", "label": "LOOKUP_PRIMARY", "description": "Primary source",
        "help": "Which API is queried first. The other becomes the fallback or complement source.",
        "choices": [("off", "Open Food Facts"), ("upcdb", "UPC Database")],
        "group": "Barcode Lookup Sources", "section": "Strategy",
    },
    "lookup_strategy": {
        "type": "choice", "label": "LOOKUP_STRATEGY", "description": "Lookup strategy",
        "help": "Failover: try secondary only when primary returns nothing. Complement: fill missing fields from the secondary source.",
        "choices": ["failover", "complement"], "group": "Barcode Lookup Sources", "section": "Strategy",
    },
    "lookup_enrich_in_background": {
        "type": "bool", "label": "LOOKUP_ENRICH_IN_BACKGROUND", "description": "Enabled",
        "form_label": "Background enrichment",
        "help": "In complement mode, run the secondary lookup after responding to the scanner for faster scans.",
        "group": "Barcode Lookup Sources", "section": "Strategy",
    },
    "fuzzy_match_threshold": {
        "type": "int", "label": "FUZZY_MATCH_THRESHOLD", "description": "Match threshold",
        "help": "Minimum score (0–100) for a barcode title to be auto-linked to a Mealie item.",
        "min": 0, "max": 100, "group": "Matching & Sync", "section": "Fuzzy Matching",
    },
    "fuzzy_ambiguity_gap": {
        "type": "int", "label": "FUZZY_AMBIGUITY_GAP", "description": "Ambiguity gap",
        "help": "Minimum score gap between the top two matches.",
        "min": 0, "max": 50, "group": "Matching & Sync", "section": "Fuzzy Matching",
    },
    "item_sync_interval_hours": {
        "type": "int", "label": "ITEM_SYNC_INTERVAL_HOURS", "description": "Sync interval",
        "help": "How often the Mealie item list is re-synced (in hours).",
        "min": 1, "max": 168, "group": "Matching & Sync", "section": "Scheduling & Retry",
    },
    "lookup_ttl_days": {
        "type": "int", "label": "LOOKUP_TTL_DAYS", "description": "Cache TTL",
        "help": "Days before a cached barcode lookup expires.",
        "min": 1, "max": 365, "group": "Matching & Sync", "section": "Scheduling & Retry",
    },
    "max_retry_attempts": {
        "type": "int", "label": "MAX_RETRY_ATTEMPTS", "description": "Max retries",
        "help": "How many times to retry adding an item to Mealie before marking it as failed.",
        "min": 1, "max": 100, "group": "Matching & Sync", "section": "Scheduling & Retry",
    },
    "unknown_barcode_action": {
        "type": "choice", "label": "UNKNOWN_BARCODE_ACTION", "description": "Unknown barcode behavior",
        "help": "Controls what happens when a scanned barcode cannot be linked.",
        "choices": [("add_to_list", "Add to list & notify"), ("notify_only", "Notify only")],
        "group": "Scanning", "section": "Unknown & Unlinked Barcodes",
    },
    "notification_toast_seconds": {
        "type": "int", "label": "NOTIFICATION_TOAST_SECONDS", "description": "Toast visibility (seconds)",
        "help": "How long scan notifications stay visible in the web UI.",
        "min": 3, "max": 120, "group": "Notifications", "section": "Web UI",
    },
    "notification_group_window_seconds": {
        "type": "int", "label": "NOTIFICATION_GROUP_WINDOW_SECONDS", "description": "Duplicate grouping window (seconds)",
        "help": "Identical scans inside this window are collapsed into one notification with a counter.",
        "min": 1, "max": 300, "group": "Notifications", "section": "Web UI",
    },
    "dashboard_poll_interval_seconds": {
        "type": "int", "label": "DASHBOARD_POLL_INTERVAL_SECONDS", "description": "Dashboard data refresh",
        "help": "How often the visible dashboard refreshes scanner state, recent scans and shopping-list counts. Scan events still refresh immediately.",
        "min": 1, "max": 300, "group": "System", "section": "Polling intervals",
    },
    "health_poll_interval_seconds": {
        "type": "int", "label": "HEALTH_POLL_INTERVAL_SECONDS", "description": "Mealie health check",
        "help": "How often the visible dashboard refreshes the Mealie connection indicator.",
        "min": 1, "max": 300, "group": "System", "section": "Polling intervals",
    },
    "shopping_print_poll_interval_seconds": {
        "type": "int", "label": "SHOPPING_PRINT_POLL_INTERVAL_SECONDS", "description": "Shopping-print Mealie sync",
        "help": "How often the shopping-list print page checks the selected Mealie list for checked, deleted or newly added items while the tab is visible.",
        "min": 1, "max": 300, "group": "System", "section": "Polling intervals",
    },
    "timezone": {
        "type": "str", "label": "TIMEZONE", "description": "Timezone",
        "hint": "IANA timezone, e.g. Europe/Berlin.", "group": "System", "section": "General",
    },
    "log_level": {
        "type": "choice", "label": "LOG_LEVEL", "description": "Log level",
        "help": "Application log verbosity.", "choices": ["DEBUG", "INFO", "WARNING", "ERROR"],
        "group": "System", "section": "General",
    },
    "ha_notification_mode": {
        "type": "choice", "label": "HA_NOTIFICATION_MODE", "description": "When to send scan webhooks",
        "help": "Choose which scan events are sent to Home Assistant.",
        "choices": [("unresolved", "Only unresolved / failed scans"), ("actionable", "All scans needing review"), ("all", "Every scan"), ("off", "Disabled")],
        "group": "Home Assistant", "section": "Notifications",
    },
    "ha_webhook_url": {
        "type": "str", "label": "HA_WEBHOOK_URL", "description": "Webhook URL",
        "help": "The middleware POSTs selected scan events to this webhook.",
        "hint": "e.g. http://homeassistant.local:8123/api/webhook/barcode-scanner", "wide": True,
        "group": "Home Assistant", "section": "Notifications",
    },
    "middleware_base_url": {
        "type": "str", "label": "MIDDLEWARE_BASE_URL", "description": "Middleware URL",
        "help": "URL used to build clickable deep links.", "hint": "e.g. http://b2m.local:9930", "wide": True,
        "group": "Home Assistant", "section": "Notifications",
    },
}


READONLY_SETTINGS: dict[str, dict[str, Any]] = {
    "mealie_url": {"label": "MEALIE_URL", "description": "Mealie URL", "group": "Mealie Connection", "section": ""},
    "mealie_api_key": {"label": "MEALIE_API_KEY", "description": "API key", "group": "Mealie Connection", "section": "", "secret": True},
    "off_url_base": {"label": "OFF_URL_BASE", "description": "API endpoint", "group": "Barcode Lookup Sources", "section": "Open Food Facts"},
    "upcdb_url_base": {"label": "UPCDB_URL_BASE", "description": "API endpoint", "group": "Barcode Lookup Sources", "section": "UPC Database"},
    "upcdb_api_key": {"label": "UPCDB_API_KEY", "description": "API key", "group": "Barcode Lookup Sources", "section": "UPC Database", "secret": True},
    "db_path": {"label": "DB_PATH", "description": "Database path", "group": "System", "section": "Infrastructure"},
    "session_max_age_days": {"label": "SESSION_MAX_AGE_DAYS", "description": "Login session duration (days)", "group": "System", "section": "Infrastructure"},
    "port": {"label": "PORT", "description": "HTTP port", "group": "System", "section": "Infrastructure"},
}


class SettingsManager:
    def __init__(self, env_settings: Settings):
        self.__dict__["_env"] = env_settings
        self.__dict__["_overrides"] = {}

    def __getattr__(self, name: str) -> Any:
        if name in self.__dict__.get("_overrides", {}):
            return self._overrides[name]
        return getattr(self._env, name)

    def __setattr__(self, name: str, value: Any):
        raise AttributeError("Use save_override() to change settings")

    def load_overrides_from_db(self) -> None:
        from app.database import SessionLocal
        from app.models import SettingsOverride
        db = SessionLocal()
        try:
            rows = db.query(SettingsOverride).all()
            overrides = {}
            stale = []
            for row in rows:
                if row.key not in EDITABLE_SETTINGS:
                    continue
                coerced = self._coerce(row.key, row.value)
                env_val = getattr(self._env, row.key)
                if coerced == env_val:
                    stale.append(row)
                else:
                    overrides[row.key] = coerced
            if stale:
                for row in stale:
                    db.delete(row)
                db.commit()
                logger.info("Pruned %d redundant override(s): %s", len(stale), ", ".join(r.key for r in stale))
            self.__dict__["_overrides"] = overrides
            if overrides:
                logger.info("Loaded %d settings override(s) from DB: %s", len(overrides), ", ".join(overrides.keys()))
        finally:
            db.close()

    def save_override(self, key: str, value: str, db) -> None:
        from app.models import SettingsOverride
        from app.utils import utcnow
        if key not in EDITABLE_SETTINGS:
            raise ValueError(f"Setting '{key}' is not editable")
        coerced = self._coerce(key, value)
        env_default = getattr(self._env, key)
        if coerced == env_default:
            self.reset_override(key, db)
            return
        existing = db.get(SettingsOverride, key)
        if existing:
            existing.value = str(value)
            existing.updated_at = utcnow()
        else:
            db.add(SettingsOverride(key=key, value=str(value)))
        db.commit()
        self.__dict__["_overrides"][key] = coerced

    def reset_override(self, key: str, db) -> None:
        from app.models import SettingsOverride
        existing = db.get(SettingsOverride, key)
        if existing:
            db.delete(existing)
            db.commit()
        self.__dict__["_overrides"].pop(key, None)

    def is_overridden(self, key: str) -> bool:
        return key in self.__dict__.get("_overrides", {})

    def get_env_default(self, key: str) -> Any:
        return getattr(self._env, key)

    def get_display_value(self, key: str) -> str:
        val = getattr(self, key)
        return "" if val is None else str(val)

    def _coerce(self, key: str, raw: str) -> Any:
        meta = EDITABLE_SETTINGS[key]
        field_type = meta["type"]
        if field_type == "bool":
            return raw.lower() in ("true", "1", "yes", "on")
        if field_type == "int":
            v = int(raw)
            if "min" in meta:
                v = max(meta["min"], v)
            if "max" in meta:
                v = min(meta["max"], v)
            return v
        if field_type == "choice":
            choices = meta["choices"]
            valid_values = [choice[0] if isinstance(choice, (tuple, list)) else choice for choice in choices]
            if raw not in valid_values:
                raise ValueError(f"Invalid choice '{raw}' for {key}")
            return raw
        return raw


_env_settings = Settings()
settings = SettingsManager(_env_settings)