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
_counts_cache: tuple[float, list[dict]] | None = None
_http = httpx.Client(
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=60.0),
)


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


def _invalidate_counts_cache() -> None:
    global _counts_cache
    with _list_cache_lock:
        _counts_cache = None


def _log_slow(operation: str, started: float) -> None:
    elapsed_ms = int((time.monotonic() - started) * 1000)
    if elapsed_ms >= 1000:
        logger.warning("Slow Mealie request: %s took %d ms", operation, elapsed_ms)


def test_mealie_connection() -> dict:
    started = time.monotonic()
    try:
        response = _http.get(
            f"{settings.mealie_url.rstrip('/')}/api/households/shopping/lists",
            headers=_headers(), params={"perPage": 1}, timeout=8,
        )
        response.raise_for_status()
        return {"ok": True, "status": response.status_code, "latency_ms": int((time.monotonic() - started) * 1000)}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "latency_ms": int((time.monotonic() - started) * 1000)}


def get_shopping_lists(force: bool = False) -> list[dict]:
    global _list_cache
    now = time.monotonic()
    with _list_cache_lock:
        if not force and _list_cache and now - _list_cache[0] < 120:
            return list(_list_cache[1])
    try:
        response = _http.get(
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


def get_default_shopping_list_id(db=None, *, force_lists: bool = False) -> str:
    """Runtime-selected default list; legacy env ID is only a fallback.

    Normal hot-path reads trust the already selected ID. Remote list discovery is
    only needed when no ID exists or when the caller explicitly asks to validate
    against Mealie. This avoids a network GET before every scan.
    """
    close_db = False
    if db is None:
        from app.database import SessionLocal
        db = SessionLocal()
        close_db = True
    try:
        from app.models import SystemState
        row = db.get(SystemState, "mealie.default_shopping_list_id")
        configured = (row.value or "").strip() if row else ""
        legacy = (getattr(settings, "mealie_shopping_list_id", "") or "").strip()

        if not force_lists:
            if configured:
                return configured
            if legacy:
                return legacy

        lists = get_shopping_lists(force=force_lists)
        available = {str(item["id"]) for item in lists}
        if configured and (not available or configured in available):
            return configured
        if legacy and (not available or legacy in available):
            return legacy
        return str(lists[0]["id"]) if lists else legacy
    finally:
        if close_db:
            db.close()


def set_default_shopping_list_id(list_id: str, db) -> str:
    from app.models import SystemState
    list_id = str(list_id or "").strip()
    available = {str(row["id"]) for row in get_shopping_lists(force=True)}
    if not list_id or list_id not in available:
        raise ValueError("Selected shopping list is not available in Mealie")
    row = db.get(SystemState, "mealie.default_shopping_list_id")
    if row:
        row.value = list_id
    else:
        db.add(SystemState(key="mealie.default_shopping_list_id", value=list_id))
    db.commit()
    return list_id


def get_shopping_list_counts(force: bool = False) -> list[dict]:
    """Return unchecked item count per Mealie shopping list."""
    global _counts_cache
    now = time.monotonic()
    with _list_cache_lock:
        if not force and _counts_cache and now - _counts_cache[0] < 20:
            return list(_counts_cache[1])
    lists = get_shopping_lists(force=force)
    counts = {str(row["id"]): 0 for row in lists}
    try:
        response = _http.get(
            f"{settings.mealie_url}/api/households/shopping/items",
            headers=_headers(), params={"perPage": -1}, timeout=10,
        )
        response.raise_for_status()
        for row in _items(response.json()):
            if not isinstance(row, dict) or row.get("checked"):
                continue
            list_id = row.get("shoppingListId")
            if not list_id and isinstance(row.get("shoppingList"), dict):
                list_id = row["shoppingList"].get("id")
            if list_id is not None:
                counts[str(list_id)] = counts.get(str(list_id), 0) + 1
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Could not count Mealie shopping items: %s", exc)
    default_id = get_default_shopping_list_id()
    result = [
        {"id": str(row["id"]), "name": row["name"], "count": counts.get(str(row["id"]), 0), "default": str(row["id"]) == str(default_id)}
        for row in lists
    ]
    with _list_cache_lock:
        _counts_cache = (now, result)
    return list(result)


def _explicit_quantity(quantity: float | None) -> float | None:
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
    started = time.monotonic()
    try:
        response = _http.post(
            f"{settings.mealie_url}/api/households/shopping/items",
            headers=_headers(), json=payload, timeout=10,
        )
        _log_slow("add food", started)
        if response.status_code in (200, 201):
            _invalidate_counts_cache()
            return True
        logger.warning("Mealie add Food returned %s: %s", response.status_code, response.text[:300])
    except httpx.HTTPError as exc:
        _log_slow("add food", started)
        logger.warning("Mealie add Food failed: %s", exc)
    return False


def add_note_to_list(note: str, list_id: str) -> bool:
    payload = {"shoppingListId": list_id, "note": note, "quantity": 1}
    started = time.monotonic()
    try:
        response = _http.post(
            f"{settings.mealie_url}/api/households/shopping/items",
            headers=_headers(), json=payload, timeout=10,
        )
        _log_slow("add note", started)
        ok = response.status_code in (200, 201)
        if ok:
            _invalidate_counts_cache()
        return ok
    except httpx.HTTPError:
        _log_slow("add note", started)
        return False


def add_recipe_to_list(recipe_id: str, scale: float, list_id: str) -> bool:
    started = time.monotonic()
    try:
        response = _http.post(
            f"{settings.mealie_url}/api/households/shopping/lists/{list_id}/recipe",
            headers=_headers(),
            json=[{"recipeId": recipe_id, "recipeIncrementQuantity": scale or 1.0}],
            timeout=15,
        )
        _log_slow("add recipe", started)
        if response.status_code in (200, 201):
            _invalidate_counts_cache()
            return True
        logger.warning("Mealie add Recipe returned %s: %s", response.status_code, response.text[:300])
    except httpx.HTTPError as exc:
        _log_slow("add recipe", started)
        logger.warning("Mealie add Recipe failed: %s", exc)
    return False


def effective_list_ids(list_ids: list[str] | None, db=None, fallback: str | None = None) -> list[str]:
    cleaned = list(dict.fromkeys(str(value).strip() for value in (list_ids or []) if str(value).strip()))
    if cleaned:
        return cleaned
    if fallback:
        return [fallback]
    default_id = get_default_shopping_list_id(db)
    return [default_id] if default_id else []


def route_item_scan(
    item: Item,
    *,
    barcode: str,
    quantity: float | None,
    unit_id: str | None,
    route_override: str | None = None,
    list_ids_override: list[str] | None = None,
    db=None,
) -> dict:
    route = (route_override or "inherit").lower()
    if route == "inherit":
        route = (item.shopping_route or "default").lower()
    if route == "default":
        route = "mealie"

    # Do not resolve the default list when the target already carries explicit
    # list IDs. Function arguments are evaluated eagerly, so the previous code
    # performed a needless DB/cache/network lookup even when it was never used.
    explicit_lists = list(dict.fromkeys(str(value).strip() for value in (list_ids_override or []) if str(value).strip()))
    if explicit_lists:
        list_ids = explicit_lists
    elif item.shopping_list_id:
        list_ids = [str(item.shopping_list_id)]
    else:
        list_ids = effective_list_ids(None, db)

    explicit_quantity = _explicit_quantity(quantity)

    mealie_required = route in {"mealie", "both"}
    ha_required = route in {"homeassistant", "both"}
    if route == "none":
        return {"ok": True, "mealie": None, "ha": None, "via": "none", "list_ids": list_ids, "list_id": list_ids[0] if list_ids else ""}

    mealie_results = []
    if mealie_required:
        for list_id in list_ids:
            if item.source == "mealie":
                mealie_results.append(add_food_to_list(item.id, explicit_quantity, unit_id, list_id))
            else:
                mealie_results.append(add_note_to_list(item.name, list_id))
        mealie_ok = bool(mealie_results) and all(mealie_results)
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
    return {
        "ok": ok,
        "mealie": mealie_ok,
        "mealie_results": mealie_results,
        "ha": ha_ok,
        "via": route,
        "list_ids": list_ids,
        "list_id": list_ids[0] if list_ids else "",
    }
