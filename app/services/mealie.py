import json
import logging

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import BarcodeCache, BarcodeMapping, Item, Activity, RetryQueue
from app.utils import utcnow

logger = logging.getLogger(__name__)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.mealie_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _collection_items(data) -> list[dict]:
    """Normalize Mealie paginated/list responses to a list of dicts."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        items = data.get("items")
        if isinstance(items, list):
            return items
    return []


def check_connectivity() -> bool:
    """Check if Mealie is reachable."""
    try:
        resp = httpx.get(
            f"{settings.mealie_url}/api/app/about",
            headers=_headers(),
            timeout=5,
        )
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


def sync_items(db: Session) -> int:
    """Fetch all foods from Mealie, upsert into items table, detect stale. Returns count."""
    url = f"{settings.mealie_url}/api/foods"
    try:
        resp = httpx.get(url, headers=_headers(), params={"perPage": -1}, timeout=30)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error(f"Failed to sync items from Mealie: {e}")
        raise

    items = _collection_items(resp.json())
    if not items and isinstance(resp.json(), dict) and "items" not in resp.json():
        logger.error(f"Unexpected Mealie response structure: {list(resp.json().keys())}")
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

        existing = db.get(Item, item_id)
        if existing:
            existing.name = name
            existing.aliases = aliases_json
            existing.synced_at = sync_started
        else:
            db.add(Item(id=item_id, name=name, source="mealie", aliases=aliases_json, synced_at=sync_started))
        count += 1

    db.flush()

    # Detect stale items (deleted in Mealie since last sync)
    stale_items = (
        db.query(Item)
        .filter(Item.source == "mealie", Item.synced_at < sync_started)
        .all()
    )
    for stale in stale_items:
        broken = db.query(BarcodeMapping).filter(BarcodeMapping.item_id == stale.id).all()
        for m in broken:
            db.add(Activity(
                barcode=m.barcode,
                title="Mapping broken",
                message=f"{stale.name} was deleted in Mealie — remap needed",
                result="broken",
            ))
            db.delete(m)
        db.delete(stale)
        if broken:
            logger.warning(f"Stale item '{stale.name}' removed, {len(broken)} mapping(s) broken")

    db.commit()
    logger.info(f"Synced {count} items from Mealie")
    return count


def get_units() -> list[dict]:
    """Return Mealie ingredient units for shopping defaults."""
    try:
        resp = httpx.get(
            f"{settings.mealie_url}/api/units",
            headers=_headers(),
            params={"perPage": -1, "orderBy": "name", "orderDirection": "asc"},
            timeout=10,
        )
        resp.raise_for_status()
        return _collection_items(resp.json())
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Failed to fetch Mealie units: %s", e)
        return []


def get_food_labels() -> list[dict]:
    """Return Mealie multi-purpose labels usable as food categories."""
    try:
        resp = httpx.get(
            f"{settings.mealie_url}/api/groups/labels",
            headers=_headers(),
            params={"perPage": -1, "orderBy": "name", "orderDirection": "asc"},
            timeout=10,
        )
        resp.raise_for_status()
        return _collection_items(resp.json())
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Failed to fetch Mealie labels: %s", e)
        return []


def get_recipes() -> list[dict]:
    """Return recipes from Mealie. Recipe IDs are used for barcode mappings."""
    try:
        resp = httpx.get(
            f"{settings.mealie_url}/api/recipes",
            headers=_headers(),
            params={"perPage": -1, "orderBy": "name", "orderDirection": "asc"},
            timeout=20,
        )
        resp.raise_for_status()
        return _collection_items(resp.json())
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Failed to fetch Mealie recipes: %s", e)
        return []


def get_recipe(recipe_id: str) -> dict | None:
    """Fetch a Mealie recipe by ID (Mealie accepts slug or ID on this endpoint)."""
    try:
        resp = httpx.get(
            f"{settings.mealie_url}/api/recipes/{recipe_id}",
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning("Mealie recipe GET %s returned %s", recipe_id, resp.status_code)
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Failed to fetch Mealie recipe %s: %s", recipe_id, e)
    return None


def create_food(
    name: str,
    plural_name: str | None = None,
    description: str | None = None,
    label_id: str | None = None,
) -> dict:
    """Create a real structured food in Mealie and return the created object."""
    payload: dict = {"name": name}
    if plural_name:
        payload["pluralName"] = plural_name
    if description:
        payload["description"] = description
    if label_id:
        payload["labelId"] = label_id

    resp = httpx.post(
        f"{settings.mealie_url}/api/foods",
        headers=_headers(),
        json=payload,
        timeout=15,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Mealie food create failed ({resp.status_code}): {resp.text}")
    data = resp.json()
    if not isinstance(data, dict) or not data.get("id"):
        raise RuntimeError("Mealie food create returned no food id")
    return data


def upsert_local_food(food: dict, db: Session) -> Item:
    """Immediately mirror a just-created Mealie food locally without waiting for sync."""
    item_id = str(food["id"])
    aliases_raw = food.get("aliases") or []
    aliases = [a.get("name", a) if isinstance(a, dict) else a for a in aliases_raw]
    item = db.get(Item, item_id)
    if item:
        item.name = food.get("name") or item.name
        item.aliases = json.dumps(aliases)
        item.source = "mealie"
        item.synced_at = utcnow()
    else:
        item = Item(
            id=item_id,
            name=food.get("name") or item_id,
            source="mealie",
            aliases=json.dumps(aliases),
            synced_at=utcnow(),
        )
        db.add(item)
    db.flush()
    return item


def add_shopping_item(
    item_id: str,
    quantity: float = 1.0,
    unit_id: str | None = None,
) -> tuple[bool, str | None]:
    """Add a structured Mealie food to the shopping list."""
    payload: dict = {
        "shoppingListId": settings.mealie_shopping_list_id,
        "foodId": item_id,
        "quantity": quantity,
    }
    if unit_id:
        payload["unitId"] = unit_id
    return _post_shopping_item(payload)


def add_shopping_note(note: str) -> tuple[bool, str | None]:
    """Add a plain note to the Mealie shopping list. Returns (success, created_item_id)."""
    payload = {
        "shoppingListId": settings.mealie_shopping_list_id,
        "note": note,
    }
    return _post_shopping_item(payload)


def add_to_shopping_list_by_item(item_id: str, quantity: float = 1.0, unit_id: str | None = None) -> bool:
    """Bool wrapper for callers that don't need the created item id."""
    return add_shopping_item(item_id, quantity=quantity, unit_id=unit_id)[0]


def add_to_shopping_list_by_note(note: str) -> bool:
    """Bool wrapper for callers that don't need the created item id."""
    return add_shopping_note(note)[0]


def add_recipe_to_shopping_list(recipe_id: str, recipe_scale: float = 1.0) -> bool:
    """Use Mealie's native recipe-to-shopping-list link.

    This deliberately does not expand ingredients in the middleware. Mealie
    creates/updates the recipe reference and owns the ingredient linkage.
    """
    url = f"{settings.mealie_url}/api/households/shopping/lists/{settings.mealie_shopping_list_id}/recipe"
    payload = [{
        "recipeId": recipe_id,
        "recipeIncrementQuantity": recipe_scale,
    }]
    try:
        resp = httpx.post(url, headers=_headers(), json=payload, timeout=15)
        if resp.status_code in (200, 201):
            return True
        logger.warning("Mealie recipe shopping POST returned %s: %s", resp.status_code, resp.text)
    except httpx.HTTPError as e:
        logger.error("Mealie recipe shopping POST failed: %s", e)
    return False


def _post_shopping_item(payload: dict) -> tuple[bool, str | None]:
    """POST to Mealie shopping items endpoint.

    Returns ``(success, created_item_id)``. ``success`` reflects the HTTP
    result only; ``created_item_id`` is the id of the newly created line
    (``createdItems[0].id`` in Mealie's ``ShoppingListItemsCollectionOut``)
    or ``None`` if it could not be parsed.
    """
    url = f"{settings.mealie_url}/api/households/shopping/items"
    try:
        resp = httpx.post(url, headers=_headers(), json=payload, timeout=3)
        if resp.status_code in (200, 201):
            item_id = None
            try:
                created = resp.json().get("createdItems") or []
                if created:
                    item_id = created[0].get("id")
            except (ValueError, TypeError, AttributeError):
                logger.warning("Mealie shopping POST succeeded but created id could not be parsed")
            return True, item_id
        logger.warning(f"Mealie shopping POST returned {resp.status_code}: {resp.text}")
        return False, None
    except httpx.HTTPError as e:
        logger.error(f"Mealie shopping POST failed: {e}")
        return False, None


def _get_shopping_item(item_id: str) -> dict | None:
    url = f"{settings.mealie_url}/api/households/shopping/items/{item_id}"
    try:
        resp = httpx.get(url, headers=_headers(), timeout=3)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code != 404:
            logger.warning(f"Mealie shopping GET {item_id} returned {resp.status_code}")
        return None
    except (httpx.HTTPError, ValueError) as e:
        logger.error(f"Mealie shopping GET {item_id} failed: {e}")
        return None


def _put_shopping_item(item_id: str, payload: dict) -> bool:
    url = f"{settings.mealie_url}/api/households/shopping/items/{item_id}"
    try:
        resp = httpx.put(url, headers=_headers(), json=payload, timeout=3)
        if resp.status_code in (200, 201):
            return True
        logger.warning(f"Mealie shopping PUT {item_id} returned {resp.status_code}: {resp.text}")
        return False
    except httpx.HTTPError as e:
        logger.error(f"Mealie shopping PUT {item_id} failed: {e}")
        return False


def reconcile_linked_barcode(barcode: str) -> None:
    """Reconcile a note/queued line after a barcode is linked to a food."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        mapping = db.get(BarcodeMapping, barcode)
        if not mapping:
            return
        item = db.get(Item, mapping.item_id)
        if not item:
            return

        pending = db.query(RetryQueue).filter(RetryQueue.barcode == barcode).all()
        rewrote = False
        for entry in pending:
            try:
                payload = json.loads(entry.payload)
            except (ValueError, TypeError):
                continue
            if item.source == "mealie":
                payload.pop("note", None)
                payload["foodId"] = item.id
                payload["quantity"] = mapping.quantity or 1
                if mapping.unit_id:
                    payload["unitId"] = mapping.unit_id
                else:
                    payload.pop("unitId", None)
            else:
                payload.pop("foodId", None)
                payload.pop("unitId", None)
                payload["note"] = item.name
            entry.payload = json.dumps(payload)
            rewrote = True
        if rewrote:
            db.commit()

        cached = db.get(BarcodeCache, barcode)
        shopping_item_id = cached.shopping_item_id if cached else None
        if not shopping_item_id:
            return

        current = _get_shopping_item(shopping_item_id)
        if current is None or current.get("checked"):
            cached.shopping_item_id = None
            db.commit()
            return

        payload = {
            "shoppingListId": current.get("shoppingListId") or settings.mealie_shopping_list_id,
            "quantity": mapping.quantity or 1,
            "checked": current.get("checked", False),
            "position": current.get("position", 0),
        }
        if item.source == "mealie":
            payload["foodId"] = item.id
            payload["note"] = ""
            payload["unitId"] = mapping.unit_id
        else:
            payload["foodId"] = None
            payload["unitId"] = None
            payload["note"] = item.name

        if _put_shopping_item(shopping_item_id, payload):
            cached.shopping_item_id = None
            db.commit()
            logger.info(
                "Reconciled shopping item %s for barcode %s -> %s",
                shopping_item_id, barcode, item.name,
            )
    finally:
        db.close()


def enqueue_retry(barcode: str, payload: dict, db: Session) -> None:
    """Add a failed Mealie request to the retry queue (skip if already pending)."""
    existing = db.query(RetryQueue).filter(RetryQueue.barcode == barcode).first()
    if existing:
        logger.info(f"Retry entry already pending for barcode={barcode}, skipping duplicate")
        return
    db.add(RetryQueue(
        barcode=barcode,
        payload=json.dumps(payload),
        attempts=0,
        next_retry_at=utcnow(),
        created_at=utcnow(),
    ))
    db.commit()
