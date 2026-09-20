from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import BarcodeTarget, Item
from app.services.homeassistant import notify_shopping_route
from app.services.mealie import enqueue_retry
from app.services.shopping import (
    add_food_to_list,
    add_note_to_list,
    add_recipe_to_list,
    get_default_shopping_list_id,
    route_item_scan,
)
from app.services.targets import target_summary

logger = logging.getLogger(__name__)


def _retry_food(barcode: str, item: Item, target: BarcodeTarget, list_id: str, db: Session) -> None:
    if item.source == "mealie":
        payload = {"shoppingListId": list_id, "foodId": item.id}
        if target.quantity is not None and target.quantity > 0.001:
            payload["quantity"] = target.quantity
        if target.unit_id:
            payload["unitId"] = target.unit_id
    else:
        payload = {"shoppingListId": list_id, "note": item.name, "quantity": 1}
    enqueue_retry(barcode, payload, db)


def _dispatch_one(db: Session, barcode: str, target: BarcodeTarget) -> dict:
    destination = (target.destination_type or "mealie").lower()
    list_id = target.shopping_list_id or get_default_shopping_list_id()

    if target.target_type == "food":
        item = db.get(Item, target.target_id)
        if not item:
            return {"ok": False, "kind": "broken", "target": target, "error": "Food no longer exists"}

        if destination == "inherit":
            routed = route_item_scan(
                item,
                barcode=barcode,
                quantity=target.quantity,
                unit_id=target.unit_id,
            )
            if routed.get("ok"):
                return {"ok": True, "kind": routed.get("via") or "inherit", "target": target}
            if routed.get("mealie") is False and routed.get("list_id"):
                _retry_food(barcode, item, target, routed["list_id"], db)
                if routed.get("ha") is not False:
                    return {"ok": True, "queued": True, "kind": "retry", "target": target}
            return {"ok": False, "kind": "inherit", "target": target, "error": "Inherited route failed"}

        if destination == "mealie":
            if not list_id:
                return {"ok": False, "kind": "mealie", "target": target, "error": "No shopping list available"}
            ok = (
                add_food_to_list(item.id, target.quantity, target.unit_id, list_id)
                if item.source == "mealie"
                else add_note_to_list(item.name, list_id)
            )
            if not ok:
                _retry_food(barcode, item, target, list_id, db)
                return {"ok": True, "queued": True, "kind": "mealie", "target": target}
            return {"ok": True, "kind": "mealie", "target": target}

        if destination in {"homeassistant", "webhook"}:
            ok = notify_shopping_route(
                barcode=barcode,
                item_id=item.id,
                item_name=item.name,
                quantity=target.quantity,
                unit_id=target.unit_id,
                route=destination,
                url_override=target.endpoint_url if destination == "webhook" else None,
                target_type="food",
                shopping_list_id=list_id,
            )
            return {"ok": ok, "kind": destination, "target": target, "error": None if ok else "Webhook failed"}

        return {"ok": False, "kind": destination, "target": target, "error": "Unsupported destination"}

    if target.target_type == "recipe":
        recipe_name = target.target_name or target.target_id
        if destination in {"inherit", "mealie"}:
            if not list_id:
                return {"ok": False, "kind": "mealie", "target": target, "error": "No shopping list available"}
            ok = add_recipe_to_list(target.target_id, target.recipe_scale or 1.0, list_id)
            return {"ok": ok, "kind": "mealie", "target": target, "error": None if ok else "Recipe add failed"}
        if destination in {"homeassistant", "webhook"}:
            ok = notify_shopping_route(
                barcode=barcode,
                item_id=target.target_id,
                item_name=recipe_name,
                quantity=target.recipe_scale or 1.0,
                unit_id=None,
                route=destination,
                url_override=target.endpoint_url if destination == "webhook" else None,
                target_type="recipe",
                shopping_list_id=list_id,
            )
            return {"ok": ok, "kind": destination, "target": target, "error": None if ok else "Webhook failed"}
        return {"ok": False, "kind": destination, "target": target, "error": "Unsupported destination"}

    return {"ok": False, "kind": destination, "target": target, "error": "Unsupported target type"}


def dispatch_barcode_targets(
    db: Session,
    barcode: str,
    targets: list[BarcodeTarget],
    *,
    paused: bool = False,
) -> dict:
    """Dispatch every target behind one barcode and summarize the scan once."""
    active = [target for target in targets if target.enabled]
    summary = target_summary(active)
    if not active:
        return {"result": "needs_mapping", "item": barcode, "via": None, "needs_action": True, "results": []}
    if paused:
        return {"result": "added", "item": summary, "via": "multi" if len(active) > 1 else "paused", "needs_action": False, "results": []}

    results = []
    for target in active:
        try:
            results.append(_dispatch_one(db, barcode, target))
        except Exception as exc:
            logger.exception("Barcode target %s failed for %s", target.id, barcode)
            results.append({"ok": False, "kind": target.destination_type, "target": target, "error": str(exc)})

    failed = [row for row in results if not row.get("ok")]
    queued = [row for row in results if row.get("queued")]
    successful = [row for row in results if row.get("ok") and not row.get("queued")]

    if failed and (successful or queued):
        result = "partial"
    elif failed:
        result = "error"
    elif queued and not successful:
        result = "queued"
    else:
        result = "added"

    via = "multi" if len(active) > 1 else (results[0].get("kind") if results else None)
    return {
        "result": result,
        "item": summary,
        "via": via,
        "needs_action": bool(failed),
        "results": results,
        "target_count": len(active),
    }
