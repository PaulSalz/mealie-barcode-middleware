"""Home Assistant webhook integration."""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def should_send_scan_webhook(result: str, needs_action: bool = False) -> bool:
    """Return whether the current HA notification mode allows this scan event."""
    mode = settings.ha_notification_mode
    if mode == "off":
        return False
    if mode == "all":
        return True
    if mode == "actionable":
        return needs_action or result in {"unknown", "needs_mapping", "error", "auto_mapped"}
    # Default: only unresolved scans. Deliberately excludes successful auto-matches
    # and transient retry-queue events to avoid notification spam.
    return result in {"unknown", "needs_mapping", "error", "retry_failed", "broken"}


def notify_scan(
    barcode: str,
    item: str | None,
    result: str,
    action_url: str,
    added_to_list: bool = True,
    paused: bool = False,
) -> None:
    """POST scan data to the HA webhook. Fire-and-forget, never raises."""
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

    try:
        resp = httpx.post(url, json=payload, timeout=3)
        if resp.status_code >= 400:
            logger.warning("HA webhook returned %d: %s", resp.status_code, resp.text[:200])
        else:
            logger.debug("HA webhook notified: %s → %s", barcode, result)
    except httpx.TimeoutException:
        logger.warning("HA webhook timed out for barcode %s", barcode)
    except Exception:
        logger.warning("HA webhook failed for barcode %s", barcode, exc_info=True)


def dismiss_notification(barcode: str, result: str | None = None) -> None:
    """Tell HA to clear a phone notification if this event type could have created one."""
    url = settings.ha_webhook_url
    if not url:
        return
    if result is not None and not should_send_scan_webhook(result, needs_action=True):
        return
    if settings.ha_notification_mode == "off":
        return

    payload = {
        "action": "clear",
        "barcode": barcode,
    }

    try:
        resp = httpx.post(url, json=payload, timeout=3)
        if resp.status_code >= 400:
            logger.warning("HA dismiss webhook returned %d: %s", resp.status_code, resp.text[:200])
        else:
            logger.debug("HA dismiss sent for barcode %s", barcode)
    except httpx.TimeoutException:
        logger.warning("HA dismiss webhook timed out for barcode %s", barcode)
    except Exception:
        logger.warning("HA dismiss webhook failed for barcode %s", barcode, exc_info=True)
