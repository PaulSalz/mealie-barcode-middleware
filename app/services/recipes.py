import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.mealie_api_key}",
        "Accept": "application/json",
    }


def _items(data) -> list[dict]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    return []


def get_recipe_by_id(recipe_id: str) -> dict | None:
    """Resolve a recipe UUID to a full recipe, using the recipe list to obtain its slug."""
    try:
        response = httpx.get(
            f"{settings.mealie_url}/api/recipes",
            headers=_headers(),
            params={"perPage": -1},
            timeout=20,
        )
        response.raise_for_status()
        summary = next((row for row in _items(response.json()) if str(row.get("id")) == str(recipe_id)), None)
        if not summary:
            return None
        slug = summary.get("slug")
        if not slug:
            return summary
        detail = httpx.get(
            f"{settings.mealie_url}/api/recipes/{slug}",
            headers=_headers(),
            timeout=15,
        )
        if detail.status_code == 200 and isinstance(detail.json(), dict):
            return detail.json()
        return summary
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Could not load recipe %s: %s", recipe_id, exc)
        return None


def normalize_recipe(recipe: dict) -> dict:
    ingredients = []
    for row in recipe.get("recipeIngredient") or recipe.get("recipeIngredients") or []:
        if not isinstance(row, dict):
            ingredients.append(str(row))
            continue
        food = row.get("food") if isinstance(row.get("food"), dict) else {}
        unit = row.get("unit") if isinstance(row.get("unit"), dict) else {}
        quantity = row.get("quantity")
        name = row.get("display") or row.get("note") or food.get("name") or "Ingredient"
        prefix = ""
        if quantity not in (None, "", 0):
            prefix += f"{quantity:g} " if isinstance(quantity, (int, float)) else f"{quantity} "
        if unit.get("name"):
            prefix += f"{unit['name']} "
        ingredients.append((prefix + str(name)).strip())

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
