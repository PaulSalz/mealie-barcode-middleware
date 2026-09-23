import json
import logging
import threading
import time

import httpx

from app.models import Activity, BarcodeMapping, BarcodeTarget, Item
from app.services import mealie_http
from app.utils import utcnow

logger = logging.getLogger(__name__)

_CACHE_TTL = 300.0
_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, list[dict]]] = {}
_refresh_locks: dict[str, threading.Lock] = {}


def _items_from_response(data) -> list[dict]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    return []


def _load_catalog(path: str, name: str) -> list[dict]:
    try:
        response = mealie_http.get(
            path,
            params={"perPage": -1, "orderBy": "name", "orderDirection": "asc"},
            timeout=10,
            log_name=f"load {name}",
        )
        response.raise_for_status()
        return _items_from_response(response.json())
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Failed to load Mealie %s: %s", name, exc)
        return []


def _refresh_lock(name: str) -> threading.Lock:
    with _cache_lock:
        return _refresh_locks.setdefault(name, threading.Lock())


def _cached(name: str, loader) -> list[dict]:
    """Small read-through cache with one in-flight refresh per catalog.

    Several open UI pages may request labels/units at once. Without the refresh
    lock every caller that observes an expired entry performs the same remote GET.
    """
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get(name)
        if entry and now - entry[0] < _CACHE_TTL:
            return list(entry[1])

    with _refresh_lock(name):
        now = time.monotonic()
        with _cache_lock:
            entry = _cache.get(name)
            if entry and now - entry[0] < _CACHE_TTL:
                return list(entry[1])
        value = loader()
        with _cache_lock:
            _cache[name] = (time.monotonic(), list(value))
        return list(value)


def cached_units() -> list[dict]:
    return _cached("units", lambda: _load_catalog("/api/units", "units"))


def cached_labels() -> list[dict]:
    return _cached("labels", lambda: _load_catalog("/api/groups/labels", "labels"))


def clear_catalog_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _food_label(food: dict) -> tuple[str | None, str | None]:
    label = food.get("label")
    if isinstance(label, dict):
        return label.get("id"), label.get("name")
    return food.get("labelId"), None


def _food_unit(food: dict) -> tuple[str | None, str | None]:
    unit = food.get("unit")
    if isinstance(unit, dict):
        return food.get("unitId") or unit.get("id"), unit.get("name") or unit.get("abbreviation")
    return food.get("unitId"), None


def sync_items_enhanced(db) -> int:
    """Mirror Mealie Foods and track actual changes separately from sync time."""
    try:
        resp = mealie_http.get(
            "/api/foods",
            params={"perPage": -1},
            timeout=30,
            log_name="sync foods",
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
        unit_id, unit_name = _food_unit(food)

        existing = db.get(Item, item_id)
        if existing:
            changed = any([
                existing.name != name,
                (existing.aliases or "[]") != aliases_json,
                existing.label_id != label_id,
                existing.label_name != label_name,
                existing.default_unit_id != unit_id,
                existing.default_unit_name != unit_name,
            ])
            existing.name = name
            existing.aliases = aliases_json
            existing.label_id = label_id
            existing.label_name = label_name
            existing.default_unit_id = unit_id
            existing.default_unit_name = unit_name
            existing.source = "mealie"
            existing.synced_at = sync_started
            if changed:
                existing.updated_at = sync_started
        else:
            db.add(Item(
                id=item_id, name=name, source="mealie", aliases=aliases_json,
                label_id=label_id, label_name=label_name,
                default_unit_id=unit_id, default_unit_name=unit_name,
                created_at=sync_started, updated_at=sync_started, synced_at=sync_started,
            ))
        count += 1

    db.flush()
    stale_items = db.query(Item).filter(Item.source == "mealie", Item.synced_at < sync_started).all()
    for stale in stale_items:
        broken = db.query(BarcodeMapping).filter(
            BarcodeMapping.target_type == "food", BarcodeMapping.target_id == stale.id,
        ).all()
        target_rows = db.query(BarcodeTarget).filter(
            BarcodeTarget.target_type == "food", BarcodeTarget.target_id == stale.id,
        ).all()
        affected = {row.barcode for row in broken} | {row.barcode for row in target_rows}
        for barcode in affected:
            db.add(Activity(
                barcode=barcode,
                title="Mapping broken",
                message=f"{stale.name} was deleted in Mealie — remap needed",
                result="broken",
            ))
        for mapping in broken:
            db.delete(mapping)
        for target in target_rows:
            db.delete(target)
        db.delete(stale)
        if affected:
            logger.warning("Stale item '%s' removed, %d barcode(s) affected", stale.name, len(affected))

    db.commit()
    # A Food sync does not change the labels/units catalog. Keeping those caches
    # avoids an unnecessary extra catalog round-trip immediately after each sync.
    logger.info("Synced %d items from Mealie", count)
    return count


def refresh_open_shopping_items_for_food(food_id: str) -> int:
    """Touch every open shopping-list entry for *food_id* so Mealie rehydrates changed Food metadata."""
    try:
        resp = mealie_http.get(
            "/api/households/shopping/items",
            params={"perPage": -1},
            timeout=10,
            log_name="load shopping items for food refresh",
        )
        resp.raise_for_status()
        items = _items_from_response(resp.json())
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        logger.warning("Could not load shopping items while refreshing Food %s: %s", food_id, exc)
        return 0

    from app.services.shopping import get_default_shopping_list_id
    default_list_id = get_default_shopping_list_id()
    updated = 0
    for item in items:
        if not isinstance(item, dict) or item.get("checked"):
            continue
        shopping_list_id = item.get("shoppingListId")
        item_food_id = item.get("foodId")
        if not item_food_id and isinstance(item.get("food"), dict):
            item_food_id = item["food"].get("id")
        if str(item_food_id or "") != str(food_id):
            continue
        item_id = item.get("id")
        if not item_id:
            continue
        payload = {
            "shoppingListId": shopping_list_id or default_list_id,
            "quantity": item.get("quantity") or 1,
            "checked": bool(item.get("checked", False)),
            "position": item.get("position", 0),
            "foodId": food_id,
            "unitId": item.get("unitId"),
            "note": item.get("note") or "",
        }
        try:
            put = mealie_http.put(
                f"/api/households/shopping/items/{item_id}",
                json=payload,
                timeout=10,
                log_name="refresh shopping item",
            )
            if put.status_code in (200, 201):
                updated += 1
            else:
                logger.warning("Refreshing shopping item %s returned %s: %s", item_id, put.status_code, put.text[:300])
        except httpx.HTTPError as exc:
            logger.warning("Refreshing shopping item %s failed: %s", item_id, exc)
    return updated
