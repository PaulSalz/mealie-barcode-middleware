import json
import logging
import threading
import time

import httpx

from app.config import settings
from app.models import Activity, BarcodeMapping, Item
from app.services.mealie import get_labels, get_units
from app.utils import utcnow

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


def _items_from_response(data) -> list[dict]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    return []


def _food_label(food: dict) -> tuple[str | None, str | None]:
    label = food.get("label")
    if isinstance(label, dict):
        return label.get("id"), label.get("name")
    label_id = food.get("labelId")
    return label_id, None


def sync_items_enhanced(db) -> int:
    """Mirror Mealie Foods and track actual changes separately from sync time."""
    try:
        resp = httpx.get(
            f"{settings.mealie_url}/api/foods",
            headers=_headers(),
            params={"perPage": -1},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("Failed to sync items from Mealie: %s", exc)
        raise

    items = _items_from_response(data)
    if isinstance(data, dict) and "items" not in data:
        raise ValueError("Mealie API returned unexpected response (no 'items' key)")

    sync_started = utcnow()
    count = 0
    for food in items:
        item_id = food.get("id")
        if not item_id:
            continue
        name = food.get("name") or food.get("label") or ""
        aliases_raw = food.get("aliases") or []
        aliases_list = [a.get("name", a) if isinstance(a, dict) else a for a in aliases_raw]
        aliases_json = json.dumps(aliases_list)
        label_id, label_name = _food_label(food)

        existing = db.get(Item, item_id)
        if existing:
            changed = any([
                existing.name != name,
                (existing.aliases or "[]") != aliases_json,
                existing.label_id != label_id,
                existing.label_name != label_name,
            ])
            existing.name = name
            existing.aliases = aliases_json
            existing.label_id = label_id
            existing.label_name = label_name
            existing.source = "mealie"
            existing.synced_at = sync_started
            if changed:
                existing.updated_at = sync_started
        else:
            db.add(Item(
                id=item_id,
                name=name,
                source="mealie",
                aliases=aliases_json,
                label_id=label_id,
                label_name=label_name,
                created_at=sync_started,
                updated_at=sync_started,
                synced_at=sync_started,
            ))
        count += 1

    db.flush()
    stale_items = db.query(Item).filter(Item.source == "mealie", Item.synced_at < sync_started).all()
    for stale in stale_items:
        broken = db.query(BarcodeMapping).filter(
            BarcodeMapping.target_type == "food",
            BarcodeMapping.target_id == stale.id,
        ).all()
        for mapping in broken:
            db.add(Activity(
                barcode=mapping.barcode,
                title="Mapping broken",
                message=f"{stale.name} was deleted in Mealie — remap needed",
                result="broken",
            ))
            db.delete(mapping)
        db.delete(stale)
        if broken:
            logger.warning("Stale item '%s' removed, %d mapping(s) broken", stale.name, len(broken))

    db.commit()
    clear_catalog_cache()
    logger.info("Synced %d items from Mealie", count)
    return count


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
        items = _items_from_response(data)
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
