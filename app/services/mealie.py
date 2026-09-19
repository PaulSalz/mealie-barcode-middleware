import json
import logging

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Activity, BarcodeCache, BarcodeMapping, Item, RetryQueue
from app.utils import utcnow

logger = logging.getLogger(__name__)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.mealie_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _items_from_response(data) -> list[dict]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        items = data.get("items")
        if isinstance(items, list):
            return items
    return []


def check_connectivity() -> bool:
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
    """Mirror Mealie Foods into the local searchable cache."""
    url = f"{settings.mealie_url}/api/foods"
    try:
        resp = httpx.get(url, headers=_headers(), params={"perPage": -1}, timeout=30)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error("Failed to sync items from Mealie: %s", e)
        raise

    data = resp.json()
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

        existing = db.get(Item, item_id)
        if existing:
            existing.name = name
            existing.aliases = aliases_json
            existing.source = "mealie"
            existing.synced_at = sync_started
        else:
            db.add(Item(id=item_id, name=name, source="mealie", aliases=aliases_json, synced_at=sync_started))
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
    logger.info("Synced %d items from Mealie", count)
    return count


def get_units() -> list[dict]:
    """Return Mealie units for quantity/unit selection."""
    try:
        resp = httpx.get(
            f"{settings.mealie_url}/api/units",
            headers=_headers(),
            params={"perPage": -1, "orderBy": "name", "orderDirection": "asc"},
            timeout=10,
        )
        resp.raise_for_status()
        return _items_from_response(resp.json())
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Failed to load Mealie units: %s", e)
        return []


def get_labels() -> list[dict]:
    """Return Mealie multi-purpose labels used as Food categories."""
    try:
        resp = httpx.get(
            f"{settings.mealie_url}/api/groups/labels",
            headers=_headers(),
            params={"perPage": -1, "orderBy": "name", "orderDirection": "asc"},
            timeout=10,
        )
        resp.raise_for_status()
        return _items_from_response(resp.json())
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Failed to load Mealie labels: %s", e)
        return []


def get_food(item_id: str) -> dict | None:
    """Fetch one Food directly from Mealie."""
    try:
        resp = httpx.get(
            f"{settings.mealie_url}/api/foods/{item_id}",
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else None
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Failed to load Mealie Food %s: %s", item_id, e)
        return None


def find_food_by_name(name: str) -> dict | None:
    """Find an exact Food-name match in Mealie, case-insensitively."""
    name = name.strip()
    if not name:
        return None
    try:
        resp = httpx.get(
            f"{settings.mealie_url}/api/foods",
            headers=_headers(),
            params={"search": name, "perPage": 100, "orderBy": "name", "orderDirection": "asc"},
            timeout=15,
        )
        resp.raise_for_status()
        wanted = name.casefold()
        for food in _items_from_response(resp.json()):
            if str(food.get("name") or "").strip().casefold() == wanted:
                return food
        return None
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Failed to search Mealie Food '%s': %s", name, e)
        return None


def _food_update_payload(existing: dict, *, name: str, plural_name: str | None, description: str | None, label_id: str | None) -> dict:
    aliases = existing.get("aliases") or []
    substitutions = []
    for sub in existing.get("substitutions") or []:
        if not isinstance(sub, dict):
            continue
        substitute_id = sub.get("substituteFoodId")
        if not substitute_id and isinstance(sub.get("substituteFood"), dict):
            substitute_id = sub["substituteFood"].get("id")
        substitutions.append({
            "substituteFoodId": substitute_id,
            "note": sub.get("note"),
        })

    return {
        "id": existing.get("id"),
        "name": name,
        "pluralName": plural_name or None,
        "description": description or "",
        "labelId": label_id or None,
        "aliases": aliases,
        "substitutions": substitutions,
        "householdsWithIngredientFood": existing.get("householdsWithIngredientFood") or [],
        "extras": existing.get("extras") or {},
    }


def update_food(
    item_id: str,
    *,
    name: str,
    plural_name: str | None = None,
    description: str | None = None,
    label_id: str | None = None,
) -> dict:
    """Update a real Mealie Food while preserving aliases/substitutions/extras."""
    existing = get_food(item_id)
    if not existing:
        raise RuntimeError("Mealie Food not found")
    payload = _food_update_payload(
        existing,
        name=name,
        plural_name=plural_name,
        description=description,
        label_id=label_id,
    )
    resp = httpx.put(
        f"{settings.mealie_url}/api/foods/{item_id}",
        headers=_headers(),
        json=payload,
        timeout=15,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Mealie food update returned {resp.status_code}: {resp.text}")
    data = resp.json()
    if not isinstance(data, dict) or not data.get("id"):
        raise RuntimeError("Mealie food update returned no Food id")
    return data


def search_recipes(query: str = "", limit: int = 20) -> list[dict]:
    params = {
        "page": 1,
        "perPage": max(1, min(limit, 100)),
        "orderBy": "name",
        "orderDirection": "asc",
    }
    if query:
        params["search"] = query
    try:
        resp = httpx.get(
            f"{settings.mealie_url}/api/recipes",
            headers=_headers(),
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        recipes = _items_from_response(resp.json())
        return [
            {
                "id": recipe.get("id"),
                "name": recipe.get("name") or recipe.get("slug") or "Unnamed recipe",
                "slug": recipe.get("slug"),
            }
            for recipe in recipes
            if recipe.get("id")
        ]
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Failed to search Mealie recipes: %s", e)
        return []


def create_food(
    name: str,
    plural_name: str | None = None,
    description: str | None = None,
    label_id: str | None = None,
) -> dict:
    """Create a real Food in Mealie and return it."""
    payload = {
        "name": name,
        "pluralName": plural_name or None,
        "description": description or "",
        "labelId": label_id or None,
        "aliases": [],
    }
    resp = httpx.post(
        f"{settings.mealie_url}/api/foods",
        headers=_headers(),
        json=payload,
        timeout=15,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Mealie food create returned {resp.status_code}: {resp.text}")
    data = resp.json()
    if not isinstance(data, dict) or not data.get("id"):
        raise RuntimeError("Mealie food create returned no Food id")
    return data


def add_shopping_item(
    item_id: str,
    quantity: float = 1.0,
    unit_id: str | None = None,
) -> tuple[bool, str | None]:
    payload = {
        "shoppingListId": settings.mealie_shopping_list_id,
        "foodId": item_id,
        "quantity": quantity,
    }
    if unit_id:
        payload["unitId"] = unit_id
    return _post_shopping_item(payload)


def add_shopping_note(note: str) -> tuple[bool, str | None]:
    return _post_shopping_item({
        "shoppingListId": settings.mealie_shopping_list_id,
        "note": note,
    })


def add_recipe_to_shopping_list(recipe_id: str, recipe_scale: float = 1.0) -> bool:
    """Use Mealie's native recipe-to-shopping-list link."""
    url = f"{settings.mealie_url}/api/households/shopping/lists/{settings.mealie_shopping_list_id}/recipe"
    payload = [{"recipeId": recipe_id, "recipeIncrementQuantity": recipe_scale}]
    try:
        resp = httpx.post(url, headers=_headers(), json=payload, timeout=20)
        if resp.status_code in (200, 201):
            return True
        logger.warning("Mealie add-recipe POST returned %s: %s", resp.status_code, resp.text)
        return False
    except httpx.HTTPError as e:
        logger.error("Mealie add-recipe POST failed: %s", e)
        return False


def add_to_shopping_list_by_item(
    item_id: str,
    quantity: float = 1.0,
    unit_id: str | None = None,
) -> bool:
    return add_shopping_item(item_id, quantity, unit_id)[0]


def add_to_shopping_list_by_note(note: str) -> bool:
    return add_shopping_note(note)[0]


def _post_shopping_item(payload: dict) -> tuple[bool, str | None]:
    url = f"{settings.mealie_url}/api/households/shopping/items"
    try:
        resp = httpx.post(url, headers=_headers(), json=payload, timeout=5)
        if resp.status_code in (200, 201):
            item_id = None
            try:
                created = resp.json().get("createdItems") or []
                if created:
                    item_id = created[0].get("id")
            except (ValueError, TypeError, AttributeError):
                logger.warning("Mealie shopping POST succeeded but created id could not be parsed")
            return True, item_id
        logger.warning("Mealie shopping POST returned %s: %s", resp.status_code, resp.text)
        return False, None
    except httpx.HTTPError as e:
        logger.error("Mealie shopping POST failed: %s", e)
        return False, None


def _get_shopping_item(item_id: str) -> dict | None:
    url = f"{settings.mealie_url}/api/households/shopping/items/{item_id}"
    try:
        resp = httpx.get(url, headers=_headers(), timeout=5)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code != 404:
            logger.warning("Mealie shopping GET %s returned %s", item_id, resp.status_code)
        return None
    except (httpx.HTTPError, ValueError) as e:
        logger.error("Mealie shopping GET %s failed: %s", item_id, e)
        return None


def _put_shopping_item(item_id: str, payload: dict) -> bool:
    url = f"{settings.mealie_url}/api/households/shopping/items/{item_id}"
    try:
        resp = httpx.put(url, headers=_headers(), json=payload, timeout=5)
        if resp.status_code in (200, 201):
            return True
        logger.warning("Mealie shopping PUT %s returned %s: %s", item_id, resp.status_code, resp.text)
        return False
    except httpx.HTTPError as e:
        logger.error("Mealie shopping PUT %s failed: %s", item_id, e)
        return False


def _delete_shopping_item(item_id: str) -> bool:
    url = f"{settings.mealie_url}/api/households/shopping/items/{item_id}"
    try:
        resp = httpx.delete(url, headers=_headers(), timeout=5)
        if resp.status_code in (200, 204):
            return True
        logger.warning("Mealie shopping DELETE %s returned %s: %s", item_id, resp.status_code, resp.text)
        return False
    except httpx.HTTPError as e:
        logger.error("Mealie shopping DELETE %s failed: %s", item_id, e)
        return False


def reconcile_linked_barcode(barcode: str) -> None:
    """Replace an earlier note/retry once a barcode gets a structured target."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        mapping = db.get(BarcodeMapping, barcode)
        if not mapping:
            return

        cached = db.get(BarcodeCache, barcode)
        shopping_item_id = cached.shopping_item_id if cached else None
        pending = db.query(RetryQueue).filter(RetryQueue.barcode == barcode).all()

        if mapping.target_type == "food":
            item = db.get(Item, mapping.target_id)
            if not item:
                return

            rewrote = False
            for entry in pending:
                try:
                    payload = json.loads(entry.payload)
                except (ValueError, TypeError):
                    continue
                payload.pop("note", None)
                payload["foodId"] = mapping.target_id
                payload["quantity"] = mapping.quantity or 1
                if mapping.unit_id:
                    payload["unitId"] = mapping.unit_id
                else:
                    payload.pop("unitId", None)
                entry.payload = json.dumps(payload)
                rewrote = True
            if rewrote:
                db.commit()

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
                "foodId": mapping.target_id,
                "unitId": mapping.unit_id,
                "note": "",
            }
            if _put_shopping_item(shopping_item_id, payload):
                cached.shopping_item_id = None
                db.commit()
                logger.info("Reconciled shopping item %s for barcode %s -> %s", shopping_item_id, barcode, item.name)
            return

        if mapping.target_type == "recipe":
            should_add_recipe = bool(pending)
            for entry in pending:
                db.delete(entry)
            if pending:
                db.commit()

            if shopping_item_id:
                current = _get_shopping_item(shopping_item_id)
                if current is not None and not current.get("checked"):
                    if _delete_shopping_item(shopping_item_id):
                        should_add_recipe = True
                cached.shopping_item_id = None
                db.commit()

            if should_add_recipe:
                if add_recipe_to_shopping_list(mapping.target_id, mapping.recipe_scale or 1.0):
                    logger.info("Reconciled barcode %s to recipe %s", barcode, mapping.target_name or mapping.target_id)
                else:
                    logger.error("Failed to reconcile barcode %s to recipe %s", barcode, mapping.target_id)
    finally:
        db.close()


def enqueue_retry(barcode: str, payload: dict, db: Session) -> None:
    existing = db.query(RetryQueue).filter(RetryQueue.barcode == barcode).first()
    if existing:
        logger.info("Retry entry already pending for barcode=%s, skipping duplicate", barcode)
        return
    db.add(RetryQueue(
        barcode=barcode,
        payload=json.dumps(payload),
        attempts=0,
        next_retry_at=utcnow(),
        created_at=utcnow(),
    ))
    db.commit()
