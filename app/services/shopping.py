import logging
import threading
import time

import httpx

from app.config import settings
from app.database import SessionLocal
from app.models import Item, SystemState
from app.services.homeassistant import notify_shopping_route

logger = logging.getLogger(__name__)
_list_cache_lock = threading.Lock()
_list_cache: tuple[float, list[dict]] | None = None
_DEFAULT_LIST_KEY = "shopping.default_list_id"


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


def _state_value(key: str) -> str:
    try:
        db = SessionLocal()
        try:
            row = db.get(SystemState, key)
            return (row.value or "").strip() if row else ""
        finally:
            db.close()
    except Exception:
        return ""


def get_default_shopping_list_id(*, force: bool = False) -> str:
    """Return the runtime-selected default list.

    The DB selection wins. MEALIE_SHOPPING_LIST_ID remains only as a backwards-
    compatible fallback. If neither is usable, the first list returned by Mealie is
    selected automatically.
    """
    lists = get_shopping_lists(force=force)
    ids = {str(row["id"]) for row in lists}
    runtime = _state_value(_DEFAULT_LIST_KEY)
    if runtime and (not ids or runtime in ids):
        return runtime
    legacy = (getattr(settings, "mealie_shopping_list_id", "") or "").strip()
    if legacy and (not ids or legacy in ids):
        return legacy
    return str(lists[0]["id"]) if lists else legacy


def set_default_shopping_list_id(list_id: str) -> dict:
    list_id = str(list_id or "").strip()
    lists = get_shopping_lists(force=True)
    selected = next((row for row in lists if str(row.get("id")) == list_id), None)
    if not selected:
        raise ValueError("Shopping list does not exist in Mealie")
    db = SessionLocal()
    try:
        row = db.get(SystemState, _DEFAULT_LIST_KEY)
        if row:
            row.value = list_id
        else:
            db.add(SystemState(key=_DEFAULT_LIST_KEY, value=list_id))
        db.commit()
    finally:
        db.close()
    return selected


def get_shopping_list_stats(*, force: bool = False) -> list[dict]:
    """Return current open/total item counts for every Mealie shopping list."""
    lists = get_shopping_lists(force=force)
    counts = {str(row["id"]): {"open_items": 0, "total_items": 0} for row in lists}
    try:
        response = httpx.get(
            f"{settings.mealie_url}/api/households/shopping/items",
            headers=_headers(), params={"perPage": -1}, timeout=10,
        )
        response.raise_for_status()
        for item in _items(response.json()):
            if not isinstance(item, dict):
                continue
            list_id = item.get("shoppingListId")
            if not list_id and isinstance(item.get("shoppingList"), dict):
                list_id = item["shoppingList"].get("id")
            list_id = str(list_id or "")
            if list_id not in counts:
                continue
            counts[list_id]["total_items"] += 1
            if not item.get("checked", False):
                counts[list_id]["open_items"] += 1
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Could not load shopping-list item counts: %s", exc)

    default_id = get_default_shopping_list_id()
    return [
        {
            **row,
            **counts.get(str(row["id"]), {"open_items": 0, "total_items": 0}),
            "default": str(row["id"]) == str(default_id),
        }
        for row in lists
    ]


def get_preferred_unit_for_food(food_id: str) -> dict | None:
    """Infer the unit currently used for this Food from an open shopping item.

    Mealie Foods themselves do not define a default unit. An existing open shopping
    item is therefore the closest concrete unit choice we can compare a barcode
    target against.
    """
    try:
        response = httpx.get(
            f"{settings.mealie_url}/api/households/shopping/items",
            headers=_headers(), params={"perPage": -1}, timeout=10,
        )
        response.raise_for_status()
        for item in _items(response.json()):
            if not isinstance(item, dict) or item.get("checked"):
                continue
            item_food_id = item.get("foodId")
            if not item_food_id and isinstance(item.get("food"), dict):
                item_food_id = item["food"].get("id")
            if str(item_food_id or "") != str(food_id):
                continue
            unit_id = item.get("unitId")
            unit = item.get("unit") if isinstance(item.get("unit"), dict) else None
            if unit_id or unit:
                return {
                    "id": str(unit_id or unit.get("id") or ""),
                    "name": (unit or {}).get("name") or (unit or {}).get("abbreviation") or "Current unit",
                }
        return None
    except (httpx.HTTPError, ValueError):
        return None


def _explicit_quantity(quantity: float | None) -> float | None:
    if quantity is None or quantity <= 0.001:
        return None
    return quantity


def add_food_to_list(food_id: str, quantity: float | None, unit_id: str | None, list_id: str | None = None) -> bool:
    list_id = list_id or get_default_shopping_list_id()
    if not list_id:
        return False
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


def add_note_to_list(note: str, list_id: str | None = None) -> bool:
    list_id = list_id or get_default_shopping_list_id()
    if not list_id:
        return False
    payload = {"shoppingListId": list_id, "note": note, "quantity": 1}
    try:
        response = httpx.post(
            f"{settings.mealie_url}/api/households/shopping/items",
            headers=_headers(), json=payload, timeout=10,
        )
        return response.status_code in (200, 201)
    except httpx.HTTPError:
        return False


def add_recipe_to_list(recipe_id: str, scale: float, list_id: str | None = None) -> bool:
    list_id = list_id or get_default_shopping_list_id()
    if not list_id:
        return False
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
    list_id = item.shopping_list_id or get_default_shopping_list_id()
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
            target_type="food",
            shopping_list_id=list_id,
        )
    else:
        ha_ok = None

    required_results = [result for result in (mealie_ok, ha_ok) if result is not None]
    ok = bool(required_results) and all(required_results)
    return {"ok": ok, "mealie": mealie_ok, "ha": ha_ok, "via": route, "list_id": list_id}
