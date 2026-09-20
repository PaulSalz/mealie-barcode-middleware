import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.mealie_api_key}", "Accept": "application/json"}


def _items(data) -> list[dict]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    return []


def get_recipe_by_id(recipe_id: str) -> dict | None:
    try:
        response = httpx.get(
            f"{settings.mealie_url}/api/recipes",
            headers=_headers(), params={"perPage": -1}, timeout=20,
        )
        response.raise_for_status()
        summary = next((row for row in _items(response.json()) if str(row.get("id")) == str(recipe_id)), None)
        if not summary:
            return None
        slug = summary.get("slug")
        if not slug:
            return summary
        detail = httpx.get(f"{settings.mealie_url}/api/recipes/{slug}", headers=_headers(), timeout=15)
        if detail.status_code == 200 and isinstance(detail.json(), dict):
            return detail.json()
        return summary
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
