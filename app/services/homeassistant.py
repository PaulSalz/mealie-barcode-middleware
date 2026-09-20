"""Home Assistant webhook integration."""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def should_send_scan_webhook(result: str, needs_action: bool = False) -> bool:
    mode = settings.ha_notification_mode
    if mode == "off":
        return False
    if mode == "all":
        return True
    if mode == "actionable":
        return needs_action or result in {
            "unknown", "unknown_action", "needs_mapping", "added_as_note", "error",
            "action_disabled", "auto_mapped", "partial",
        }
    return result in {
        "unknown", "unknown_action", "needs_mapping", "added_as_note", "error",
        "action_disabled", "retry_failed", "broken", "partial",
    }


def notify_scan(
    barcode: str,
    item: str | None,
    result: str,
    action_url: str,
    added_to_list: bool = True,
    paused: bool = False,
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


def notify_shopping_route(
    *,
    barcode: str,
    item_id: str | None,
    item_name: str,
    quantity: float | None = 1.0,
    unit_id: str | None = None,
    route: str = "homeassistant",
    url_override: str | None = None,
    target_type: str = "food",
    shopping_list_id: str | None = None,
) -> bool:
    """Send one independently-routed target event.

    ``url_override`` lets an individual barcode target use a separate endpoint;
    when omitted the existing global Home Assistant webhook remains the default.
    """
    url = (url_override or settings.ha_webhook_url or "").strip()
    if not url:
        return False
    payload = {
        "action": "shopping_route",
        "result_type": "shopping_route",
        "barcode": barcode,
        "target_type": target_type,
        "item_id": item_id,
        "item": item_name,
        "quantity": quantity,
        "unit_id": unit_id,
        "route": route,
        "shopping_list_id": shopping_list_id,
    }
    try:
        resp = httpx.post(url, json=payload, timeout=5)
        if resp.status_code >= 400:
            logger.warning("Shopping-route webhook returned %d: %s", resp.status_code, resp.text[:200])
            return False
        return True
    except Exception:
        logger.warning("Shopping-route webhook failed for barcode %s", barcode, exc_info=True)
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

    try:
        resp = httpx.post(url, json=payload, timeout=3)
        if resp.status_code >= 400:
            logger.warning("HA dismiss webhook returned %d: %s", resp.status_code, resp.text[:200])
        else:
            _mark_actionable_dismissed(barcode)
            logger.debug("HA dismiss sent for barcode %s", barcode)
    except httpx.TimeoutException:
        logger.warning("HA dismiss webhook timed out for barcode %s", barcode)
    except Exception:
        logger.warning("HA dismiss webhook failed for barcode %s", barcode, exc_info=True)
