import logging
import threading
import time

import httpx

from app.config import settings
from app.services.mealie import get_labels, get_units

logger = logging.getLogger(__name__)

_CACHE_TTL = 300.0
_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, list[dict]]] = {}


def _cached(name: str, loader) -> list[dict]:
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get(name)
        if entry and now - entry[0] < _CACHE_TTL:
            return entry[1]
    value = loader()
    with _cache_lock:
        _cache[name] = (now, value)
    return value


def cached_units() -> list[dict]:
    return _cached("units", get_units)


def cached_labels() -> list[dict]:
    return _cached("labels", get_labels)


def clear_catalog_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.mealie_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def refresh_open_shopping_items_for_food(food_id: str) -> int:
    """Touch open shopping-list entries for *food_id* so Mealie rehydrates changed Food metadata."""
    try:
        resp = httpx.get(
            f"{settings.mealie_url}/api/households/shopping/items",
            headers=_headers(),
            params={"perPage": -1},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", []) if isinstance(data, dict) else []
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        logger.warning("Could not load shopping items while refreshing Food %s: %s", food_id, exc)
        return 0

    updated = 0
    for item in items:
        if not isinstance(item, dict) or item.get("checked"):
            continue
        shopping_list_id = item.get("shoppingListId")
        if shopping_list_id and str(shopping_list_id) != str(settings.mealie_shopping_list_id):
            continue
        item_food_id = item.get("foodId")
        if not item_food_id and isinstance(item.get("food"), dict):
            item_food_id = item["food"].get("id")
        if str(item_food_id or "") != str(food_id):
            continue

        item_id = item.get("id")
        if not item_id:
            continue
        payload = {
            "shoppingListId": shopping_list_id or settings.mealie_shopping_list_id,
            "quantity": item.get("quantity") or 1,
            "checked": bool(item.get("checked", False)),
            "position": item.get("position", 0),
            "foodId": food_id,
            "unitId": item.get("unitId"),
            "note": item.get("note") or "",
        }
        try:
            put = httpx.put(
                f"{settings.mealie_url}/api/households/shopping/items/{item_id}",
                headers=_headers(),
                json=payload,
                timeout=10,
            )
            if put.status_code in (200, 201):
                updated += 1
            else:
                logger.warning("Refreshing shopping item %s returned %s: %s", item_id, put.status_code, put.text[:300])
        except httpx.HTTPError as exc:
            logger.warning("Refreshing shopping item %s failed: %s", item_id, exc)
    return updated
