"""Home Assistant webhook integration."""

import logging
import re
import time
from urllib.parse import unquote, urlsplit

import httpx

from app.config import settings

logger = logging.getLogger(__name__)
_http = httpx.Client(
    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5, keepalive_expiry=60.0),
)


def _log_slow(operation: str, started: float) -> None:
    elapsed_ms = int((time.monotonic() - started) * 1000)
    if elapsed_ms >= 1000:
        logger.warning("Slow Home Assistant webhook: %s took %d ms", operation, elapsed_ms)


def should_send_scan_webhook(result: str, needs_action: bool = False) -> bool:
    mode = settings.ha_notification_mode
    if mode == "off":
        return False
    if mode == "all":
        return True
    if mode == "actionable":
        return needs_action or result in {
            "unknown", "unknown_action", "needs_mapping", "added_as_note", "error",
            "action_disabled", "auto_mapped",
        }
    return result in {
        "unknown", "unknown_action", "needs_mapping", "added_as_note", "error",
        "action_disabled", "retry_failed", "broken",
    }


def notify_scan(
    barcode: str,
    item: str | None,
    result: str,
    action_url: str,
    added_to_list: bool = True,
    paused: bool = False,
    scan_details: dict | None = None,
) -> None:
    url = settings.ha_webhook_url
    if not url:
        return

    payload = {
        "barcode": barcode,
        "item": item or barcode,
        "result_type": result,
        "action_url": action_url,
        "added_to_list": added_to_list,
        "paused": paused,
    }
    if scan_details:
        payload.update({key: value for key, value in scan_details.items() if key not in payload and value is not None})

    started = time.monotonic()
    try:
        resp = _http.post(url, json=payload, timeout=3)
        _log_slow("scan notification", started)
        if resp.status_code >= 400:
            logger.warning("HA webhook returned %d: %s", resp.status_code, resp.text[:200])
        else:
            logger.debug("HA webhook notified: %s → %s", barcode, result)
    except httpx.TimeoutException:
        _log_slow("scan notification", started)
        logger.warning("HA webhook timed out for barcode %s", barcode)
    except Exception:
        _log_slow("scan notification", started)
        logger.warning("HA webhook failed for barcode %s", barcode, exc_info=True)


def notify_shopping_route(
    *,
    barcode: str,
    item_id: str | None,
    item_name: str,
    quantity: float = 1.0,
    unit_id: str | None = None,
    route: str = "homeassistant",
) -> bool:
    """Send a shopping-routing event to HA regardless of notification mode.

    Reuses HA_WEBHOOK_URL so existing installations do not need another secret.
    The automation can distinguish this from notification traffic via
    result_type=shopping_route.
    """
    url = settings.ha_webhook_url
    if not url:
        return False
    payload = {
        "action": "shopping_route",
        "result_type": "shopping_route",
        "barcode": barcode,
        "item_id": item_id,
        "item": item_name,
        "quantity": quantity,
        "unit_id": unit_id,
        "route": route,
    }
    started = time.monotonic()
    try:
        resp = _http.post(url, json=payload, timeout=3)
        _log_slow("shopping route", started)
        if resp.status_code >= 400:
            logger.warning("HA shopping route returned %d: %s", resp.status_code, resp.text[:200])
            return False
        return True
    except Exception:
        _log_slow("shopping route", started)
        logger.warning("HA shopping route failed for barcode %s", barcode, exc_info=True)
        return False


def _last_actionable_result(barcode: str) -> str | None:
    try:
        from app.database import SessionLocal
        from app.models import Activity

        db = SessionLocal()
        try:
            row = (
                db.query(Activity)
                .filter(Activity.barcode == barcode, Activity.is_dismissed == False)
                .order_by(Activity.created_at.desc())
                .first()
            )
            return row.result if row else None
        finally:
            db.close()
    except Exception:
        logger.debug("Could not resolve prior notification type for %s", barcode, exc_info=True)
        return None


def _mark_actionable_dismissed(barcode: str) -> None:
    try:
        from app.database import SessionLocal
        from app.models import Activity

        db = SessionLocal()
        try:
            db.query(Activity).filter(
                Activity.barcode == barcode,
                Activity.is_dismissed == False,
            ).update({"is_dismissed": True, "is_read": True})
            db.commit()
        finally:
            db.close()
    except Exception:
        logger.debug("Could not mark notification dismissed for %s", barcode, exc_info=True)


def dismiss_notification(barcode: str, result: str | None = None) -> None:
    url = settings.ha_webhook_url
    if not url or settings.ha_notification_mode == "off":
        return

    result = result or _last_actionable_result(barcode)
    if result is None or not should_send_scan_webhook(result, needs_action=True):
        return

    payload = {"action": "clear", "barcode": barcode}

    started = time.monotonic()
    try:
        resp = _http.post(url, json=payload, timeout=3)
        _log_slow("dismiss notification", started)
        if resp.status_code >= 400:
            logger.warning("HA dismiss webhook returned %d: %s", resp.status_code, resp.text[:200])
        else:
            _mark_actionable_dismissed(barcode)
            logger.debug("HA dismiss sent for barcode %s", barcode)
    except httpx.TimeoutException:
        _log_slow("dismiss notification", started)
        logger.warning("HA dismiss webhook timed out for barcode %s", barcode)
    except Exception:
        _log_slow("dismiss notification", started)
        logger.warning("HA dismiss webhook failed for barcode %s", barcode, exc_info=True)



def homeassistant_webhook_id(url: str | None) -> str | None:
    """Return a safe Home Assistant webhook ID from a configured webhook URL."""
    if not url:
        return None
    try:
        path = urlsplit(url.strip()).path
        match = re.fullmatch(r"/api/webhook/([^/]+)/?", path)
        if not match:
            return None
        webhook_id = unquote(match.group(1))
        return webhook_id if re.fullmatch(r"[A-Za-z0-9_-]+", webhook_id) else None
    except (TypeError, ValueError):
        return None


def build_scan_notification_automation(webhook_url: str | None) -> str:
    """Build a concise HA automation for final B2M scan results."""
    webhook_id = homeassistant_webhook_id(webhook_url) or "YOUR_WEBHOOK_ID"
    yaml = """alias: B2M - Scan notification
description: Show the final result and barcode status for each B2M scan.
triggers:
  - trigger: webhook
    webhook_id: '__WEBHOOK_ID__'
    allowed_methods:
      - POST
    local_only: true
conditions:
  - condition: template
    value_template: >-
      {% set scan = ((trigger | default({})).json | default({})) %}
      {{ scan.get('result_type', '') != 'processing' }}
actions:
  - action: persistent_notification.create
    data:
      title: >-
        {% set scan = ((trigger | default({})).json | default({})) %}
        {% set state = scan.get('barcode_state', 'unknown') %}
        {% if state == 'linked' %}B2M · Verknüpft
        {% elif state == 'pending' %}B2M · Noch nicht verknüpft
        {% elif state == 'action' %}B2M · Aktion
        {% elif state == 'generic' %}B2M · Code
        {% elif state == 'error' %}B2M · Fehler
        {% else %}B2M · Unbekannter Barcode{% endif %}
      message: >-
        {% set scan = ((trigger | default({})).json | default({})) %}
        Barcode: {{ scan.get('barcode', '—') }}
        Artikel: {{ scan.get('item', '—') }}
        Status: {{ scan.get('barcode_state', 'unknown') }}
        Bekannt: {{ scan.get('barcode_known') if scan.get('barcode_known') is not none else '—' }}
        Verknüpft: {{ scan.get('barcode_linked') if scan.get('barcode_linked') is not none else '—' }}
        Ausstehend: {{ scan.get('barcode_pending') if scan.get('barcode_pending') is not none else '—' }}
        Ergebnis: {{ scan.get('result_type', '—') }}
        Quelle: {{ scan.get('via', '—') }}
        Aktion nötig: {{ scan.get('needs_action', '—') }}
        Marke: {{ scan.get('brand', '—') }}
        Menge: {{ scan.get('quantity', '—') }}
        Quelle des Artikels: {{ scan.get('item_source', '—') }}
        Zur Liste hinzugefügt: {{ scan.get('added_to_list', '—') }}
        Pausiert: {{ scan.get('paused', '—') }}
        Link: {{ scan.get('action_url', '—') }}
mode: queued
max: 10
"""
    return yaml.replace("__WEBHOOK_ID__", webhook_id)
