import logging
import threading
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_CATALOG_TTL = 180.0
_DETAIL_TTL = 300.0
_cache_lock = threading.Lock()
_catalog_cache: tuple[float, list[dict]] | None = None
_detail_cache: dict[str, tuple[float, dict]] = {}


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.mealie_api_key}", "Accept": "application/json"}


def _items(data) -> list[dict]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    return []


def _recipe_catalog() -> list[dict]:
    global _catalog_cache
    now = time.monotonic()
    with _cache_lock:
        cached = _catalog_cache
        if cached and now - cached[0] < _CATALOG_TTL:
            return cached[1]
    response = httpx.get(
        f"{settings.mealie_url}/api/recipes",
        headers=_headers(), params={"perPage": -1}, timeout=20,
    )
    response.raise_for_status()
    rows = _items(response.json())
    with _cache_lock:
        _catalog_cache = (now, rows)
    return rows


def get_recipe_by_id(recipe_id: str) -> dict | None:
    recipe_id = str(recipe_id)
    now = time.monotonic()
    with _cache_lock:
        cached = _detail_cache.get(recipe_id)
        if cached and now - cached[0] < _DETAIL_TTL:
            return cached[1]
    try:
        summary = next((row for row in _recipe_catalog() if str(row.get("id")) == recipe_id), None)
        if not summary:
            return None
        slug = summary.get("slug")
        result = summary
        if slug:
            detail = httpx.get(f"{settings.mealie_url}/api/recipes/{slug}", headers=_headers(), timeout=15)
            if detail.status_code == 200:
                data = detail.json()
                if isinstance(data, dict):
                    result = data
        with _cache_lock:
            _detail_cache[recipe_id] = (time.monotonic(), result)
        return result
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Could not load recipe %s: %s", recipe_id, exc)
        return None


def _quantity_text(value) -> str:
    if value in (None, "", 0):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (int, float)):
        return f"{value:g}"
    return str(value).strip()


def normalize_recipe(recipe: dict) -> dict:
    ingredients = []
    for row in recipe.get("recipeIngredient") or recipe.get("recipeIngredients") or []:
        if not isinstance(row, dict):
            ingredients.append({"quantity": "", "unit": "", "name": str(row), "note": ""})
            continue
        food = row.get("food") if isinstance(row.get("food"), dict) else {}
        unit = row.get("unit") if isinstance(row.get("unit"), dict) else {}
        quantity = _quantity_text(row.get("quantity"))
        unit_name = str(unit.get("name") or unit.get("abbreviation") or "").strip()
        food_name = str(food.get("name") or "").strip()
        note = str(row.get("note") or "").strip()
        display = str(row.get("display") or "").strip()

        # Prefer Mealie's structured Food name. `display` often already contains
        # quantity+unit, so prefixing it caused e.g. "100 Gramm 100 Gramm Zucchini".
        name = food_name or display or note or "Ingredient"
        if not food_name and display:
            # For unstructured rows the display is already complete; don't add a
            # second quantity/unit prefix.
            quantity = ""
            unit_name = ""
            note = "" if note == display else note
        ingredients.append({
            "quantity": quantity,
            "unit": unit_name,
            "name": name,
            "note": note if note and note != name else "",
        })

    return {
        "id": recipe.get("id"),
        "name": recipe.get("name") or recipe.get("slug") or "Recipe",
        "slug": recipe.get("slug"),
        "description": recipe.get("description") or "",
        "recipe_yield": recipe.get("recipeYield") or recipe.get("recipeServings"),
        "prep_time": recipe.get("prepTime"),
        "cook_time": recipe.get("cookTime"),
        "total_time": recipe.get("totalTime"),
        "ingredients": ingredients,
    }
