import logging
import threading
import time

import httpx

from app.config import settings
from app.models import Item
from app.services.homeassistant import notify_shopping_route

logger = logging.getLogger(__name__)
_list_cache_lock = threading.Lock()
_list_cache: tuple[float, list[dict]] | None = None


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.mealie_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _items(data) -> list[dict]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    return []


def get_shopping_lists(force: bool = False) -> list[dict]:
    global _list_cache
    now = time.monotonic()
    with _list_cache_lock:
        if not force and _list_cache and now - _list_cache[0] < 120:
            return list(_list_cache[1])
    try:
        response = httpx.get(
            f"{settings.mealie_url}/api/households/shopping/lists",
            headers=_headers(), params={"perPage": -1}, timeout=10,
        )
        response.raise_for_status()
        rows = [
            {"id": str(row.get("id")), "name": row.get("name") or "Shopping list"}
            for row in _items(response.json()) if row.get("id")
        ]
        with _list_cache_lock:
            _list_cache = (now, rows)
        return list(rows)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Could not load Mealie shopping lists: %s", exc)
        with _list_cache_lock:
            return list(_list_cache[1]) if _list_cache else []


def _explicit_quantity(quantity: float | None) -> float | None:
    """0.001 is the legacy DB-safe sentinel for 'no explicit quantity'."""
    if quantity is None or quantity <= 0.001:
        return None
    return quantity


def add_food_to_list(food_id: str, quantity: float | None, unit_id: str | None, list_id: str) -> bool:
    payload = {"shoppingListId": list_id, "foodId": food_id}
    quantity = _explicit_quantity(quantity)
    if quantity is not None:
        payload["quantity"] = quantity
    if unit_id:
        payload["unitId"] = unit_id
    try:
        response = httpx.post(
            f"{settings.mealie_url}/api/households/shopping/items",
            headers=_headers(), json=payload, timeout=10,
        )
        if response.status_code in (200, 201):
            return True
        logger.warning("Mealie add Food returned %s: %s", response.status_code, response.text[:300])
    except httpx.HTTPError as exc:
        logger.warning("Mealie add Food failed: %s", exc)
    return False


def add_note_to_list(note: str, list_id: str) -> bool:
    payload = {"shoppingListId": list_id, "note": note, "quantity": 1}
    try:
        response = httpx.post(
            f"{settings.mealie_url}/api/households/shopping/items",
            headers=_headers(), json=payload, timeout=10,
        )
        return response.status_code in (200, 201)
    except httpx.HTTPError:
        return False


def add_recipe_to_list(recipe_id: str, scale: float, list_id: str) -> bool:
    try:
        response = httpx.post(
            f"{settings.mealie_url}/api/households/shopping/lists/{list_id}/recipe",
            headers=_headers(),
            json=[{"recipeId": recipe_id, "recipeIncrementQuantity": scale or 1.0}],
            timeout=15,
        )
        if response.status_code in (200, 201):
            return True
        logger.warning("Mealie add Recipe returned %s: %s", response.status_code, response.text[:300])
    except httpx.HTTPError as exc:
        logger.warning("Mealie add Recipe failed: %s", exc)
    return False


def route_item_scan(
    item: Item,
    *,
    barcode: str,
    quantity: float | None,
    unit_id: str | None,
) -> dict:
    route = (item.shopping_route or "default").lower()
    if route == "default":
        route = "mealie"
    list_id = item.shopping_list_id or settings.mealie_shopping_list_id
    explicit_quantity = _explicit_quantity(quantity)

    mealie_required = route in {"mealie", "both"}
    ha_required = route in {"homeassistant", "both"}
    if route == "none":
        return {"ok": True, "mealie": None, "ha": None, "via": "none", "list_id": list_id}

    if mealie_required:
        if item.source == "mealie":
            mealie_ok = add_food_to_list(item.id, explicit_quantity, unit_id, list_id)
        else:
            mealie_ok = add_note_to_list(item.name, list_id)
    else:
        mealie_ok = None

    if ha_required:
        ha_ok = notify_shopping_route(
            barcode=barcode,
            item_id=item.id,
            item_name=item.name,
            quantity=explicit_quantity,
            unit_id=unit_id,
            route=route,
        )
    else:
        ha_ok = None

    required_results = [result for result in (mealie_ok, ha_ok) if result is not None]
    ok = bool(required_results) and all(required_results)
    return {"ok": ok, "mealie": mealie_ok, "ha": ha_ok, "via": route, "list_id": list_id}
