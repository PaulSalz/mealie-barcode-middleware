from __future__ import annotations

import json
import logging
from copy import deepcopy

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import SystemState
from app.services.mealie import get_labels
from app.services.shopping import get_shopping_lists

logger = logging.getLogger(__name__)

_SETTINGS_KEY = "shopping_print.settings"
_CATEGORY_ORDERS_KEY = "shopping_print.category_orders"
_CATEGORY_ALIASES_KEY = "shopping_print.category_aliases"

DEFAULT_PRINT_SETTINGS = {
    "paper_width_mm": 50.0,
    "margin_mm": 2.2,
    "body_font_mm": 3.0,
    "line_gap_mm": 0.8,
    "category_gap_mm": 1.6,
    "bottom_margin_mm": 3.0,
    "dpi": 300,
    "density": 3,
    "threshold": 145,
    # NIIMBOT paper type 3 = continuous stock (1 = gap/die-cut labels).
    "label_type": 3,
    "show_checkboxes": True,
    "show_item_names": True,
    "show_quantities": True,
    "show_item_dividers": False,
    "show_category_dividers": True,
    "category_divider_style": "solid",
}

_http = httpx.Client(
    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5, keepalive_expiry=60.0),
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


def _checked(row: dict) -> bool:
    value = row.get("checked", row.get("isChecked", False))
    if isinstance(value, str):
        value = value.strip().casefold() in {"1", "true", "yes", "on"}
    if bool(value):
        return True
    return bool(row.get("checkedAt") or row.get("completedAt"))


def _row_list_id(row: dict) -> str:
    value = row.get("shoppingListId")
    if value is None and isinstance(row.get("shoppingList"), dict):
        value = row["shoppingList"].get("id")
    return str(value or "")


def _state_json(db: Session, key: str, default):
    row = db.get(SystemState, key)
    if not row or not row.value:
        return deepcopy(default)
    try:
        value = json.loads(row.value)
    except (TypeError, ValueError):
        return deepcopy(default)
    return value


def _save_state_json(db: Session, key: str, value) -> None:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    row = db.get(SystemState, key)
    if row:
        row.value = encoded
    else:
        db.add(SystemState(key=key, value=encoded))
    db.commit()


def _boolean(values: dict, name: str) -> bool:
    value = values.get(name, DEFAULT_PRINT_SETTINGS[name])
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on"}
    return bool(value)


def load_print_settings(db: Session) -> dict:
    raw = _state_json(db, _SETTINGS_KEY, DEFAULT_PRINT_SETTINGS)
    if not isinstance(raw, dict):
        raw = {}
    merged = dict(DEFAULT_PRINT_SETTINGS)
    merged.update({key: raw[key] for key in DEFAULT_PRINT_SETTINGS if key in raw})
    return validate_print_settings(merged)


def validate_print_settings(values: dict) -> dict:
    def number(name: str, minimum: float, maximum: float) -> float:
        try:
            value = float(values.get(name, DEFAULT_PRINT_SETTINGS[name]))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid {name}") from exc
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
        return value

    def integer(name: str, minimum: int, maximum: int) -> int:
        try:
            value = int(values.get(name, DEFAULT_PRINT_SETTINGS[name]))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid {name}") from exc
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")
        return value

    divider_style = str(values.get("category_divider_style") or DEFAULT_PRINT_SETTINGS["category_divider_style"]).strip().lower()
    if divider_style not in {"solid", "dashed"}:
        raise ValueError("category_divider_style must be solid or dashed")

    return {
        "paper_width_mm": round(number("paper_width_mm", 20, 80), 1),
        "margin_mm": round(number("margin_mm", 0, 8), 1),
        "body_font_mm": round(number("body_font_mm", 2.0, 5.0), 1),
        "line_gap_mm": round(number("line_gap_mm", 0, 3), 1),
        "category_gap_mm": round(number("category_gap_mm", 0, 5), 1),
        "bottom_margin_mm": round(number("bottom_margin_mm", 0, 10), 1),
        "dpi": integer("dpi", 100, 1200),
        "density": integer("density", 1, 5),
        "threshold": integer("threshold", 1, 255),
        "label_type": integer("label_type", 1, 20),
        "show_checkboxes": _boolean(values, "show_checkboxes"),
        "show_item_names": _boolean(values, "show_item_names"),
        "show_quantities": _boolean(values, "show_quantities"),
        "show_item_dividers": _boolean(values, "show_item_dividers"),
        "show_category_dividers": _boolean(values, "show_category_dividers"),
        "category_divider_style": divider_style,
    }


def save_print_settings(db: Session, values: dict) -> dict:
    clean = validate_print_settings(values)
    _save_state_json(db, _SETTINGS_KEY, clean)
    return clean


def load_category_orders(db: Session) -> dict[str, list[str]]:
    raw = _state_json(db, _CATEGORY_ORDERS_KEY, {})
    if not isinstance(raw, dict):
        return {}
    result: dict[str, list[str]] = {}
    for list_id, names in raw.items():
        if not isinstance(names, list):
            continue
        clean = []
        seen = set()
        for name in names:
            text = str(name or "").strip()
            key = text.casefold()
            if text and key not in seen:
                clean.append(text)
                seen.add(key)
        result[str(list_id)] = clean
    return result


def save_category_order(db: Session, list_id: str, order: list[str]) -> list[str]:
    list_id = str(list_id or "").strip()
    if not list_id:
        raise ValueError("Shopping list id is required")
    clean = []
    seen = set()
    for name in order:
        text = str(name or "").strip()
        key = text.casefold()
        if text and key not in seen:
            clean.append(text)
            seen.add(key)
    rows = load_category_orders(db)
    rows[list_id] = clean
    _save_state_json(db, _CATEGORY_ORDERS_KEY, rows)
    return clean


def load_category_aliases(db: Session) -> dict[str, dict[str, str]]:
    raw = _state_json(db, _CATEGORY_ALIASES_KEY, {})
    if not isinstance(raw, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for list_id, aliases in raw.items():
        if not isinstance(aliases, dict):
            continue
        clean: dict[str, str] = {}
        for source, alias in aliases.items():
            source_name = str(source or "").strip()
            alias_name = str(alias or "").strip()
            if source_name and alias_name and alias_name.casefold() != source_name.casefold():
                clean[source_name] = alias_name[:120]
        result[str(list_id)] = clean
    return result


def save_category_aliases(db: Session, list_id: str, aliases: dict[str, str]) -> dict[str, str]:
    list_id = str(list_id or "").strip()
    if not list_id:
        raise ValueError("Shopping list id is required")
    if not isinstance(aliases, dict):
        raise ValueError("category_aliases object required")
    clean: dict[str, str] = {}
    for source, alias in aliases.items():
        source_name = str(source or "").strip()
        alias_name = str(alias or "").strip()
        if not source_name:
            continue
        if len(source_name) > 120 or len(alias_name) > 120:
            raise ValueError("Category aliases may be at most 120 characters")
        if alias_name and alias_name.casefold() != source_name.casefold():
            clean[source_name] = alias_name
    rows = load_category_aliases(db)
    rows[list_id] = clean
    _save_state_json(db, _CATEGORY_ALIASES_KEY, rows)
    return clean


def _category_name(row: dict, label_names: dict[str, str]) -> str:
    food = row.get("food") if isinstance(row.get("food"), dict) else {}
    candidates = [
        row.get("label"),
        row.get("category"),
        row.get("section"),
        row.get("foodLabel"),
        food.get("label"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            name = str(candidate.get("name") or candidate.get("label") or "").strip()
        else:
            name = str(candidate or "").strip()
        if name:
            return name

    label_id = row.get("labelId") or food.get("labelId")
    if label_id is not None:
        name = label_names.get(str(label_id))
        if name:
            return name
    return "Other"


def _item_name(row: dict) -> str:
    food = row.get("food") if isinstance(row.get("food"), dict) else {}
    return str(
        food.get("name")
        or row.get("note")
        or row.get("name")
        or row.get("display")
        or "Item"
    ).strip()


def _quantity_text(row: dict) -> str:
    quantity = row.get("quantity")
    if quantity is None or quantity == "":
        return ""
    try:
        number = float(quantity)
        if number.is_integer():
            quantity_text = str(int(number))
        else:
            quantity_text = f"{number:.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        quantity_text = str(quantity).strip()

    unit = row.get("unit") if isinstance(row.get("unit"), dict) else {}
    if not unit and isinstance(row.get("shoppingListItemUnit"), dict):
        unit = row["shoppingListItemUnit"]
    unit_text = ""
    if unit:
        use_abbreviation = bool(unit.get("useAbbreviation"))
        unit_text = str(
            (unit.get("abbreviation") if use_abbreviation else None)
            or unit.get("name")
            or unit.get("abbreviation")
            or ""
        ).strip()
    return f"{quantity_text} {unit_text}".strip()


def _normalized_item(row: dict, label_names: dict[str, str]) -> dict:
    return {
        "id": str(row.get("id") or ""),
        "name": _item_name(row),
        "quantity": row.get("quantity"),
        "quantity_text": _quantity_text(row),
        "category": _category_name(row, label_names),
        "food_id": str(row.get("foodId") or ((row.get("food") or {}).get("id") if isinstance(row.get("food"), dict) else "") or ""),
    }


def get_open_shopping_items(list_id: str) -> list[dict]:
    list_id = str(list_id or "").strip()
    if not list_id:
        return []

    label_names = {
        str(row.get("id")): str(row.get("name") or "").strip()
        for row in get_labels()
        if isinstance(row, dict) and row.get("id") and row.get("name")
    }
    try:
        response = _http.get(
            f"{settings.mealie_url.rstrip('/')}/api/households/shopping/items",
            headers=_headers(),
            params={"perPage": -1, "checked": "false", "shoppingListId": list_id},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Could not load Mealie shopping list %s for printing: %s", list_id, exc)
        raise RuntimeError(f"Could not load shopping list from Mealie: {exc}") from exc

    result = []
    for row in _items(payload):
        if not isinstance(row, dict) or _checked(row):
            continue
        row_list_id = _row_list_id(row)
        if row_list_id and row_list_id != list_id:
            continue
        result.append(_normalized_item(row, label_names))
    return result


def ordered_categories(categories: list[str], configured: list[str]) -> list[str]:
    available = {name.casefold(): name for name in categories if name}
    result = []
    used = set()
    for configured_name in configured:
        key = configured_name.casefold()
        if key in available and key not in used:
            result.append(available[key])
            used.add(key)
    for name in sorted(categories, key=str.casefold):
        key = name.casefold()
        if key not in used:
            result.append(name)
            used.add(key)
    return result


def shopping_list_payload(db: Session, list_id: str) -> dict:
    lists = get_shopping_lists(force=False)
    selected = next((row for row in lists if str(row.get("id")) == str(list_id)), None)
    if not selected:
        raise ValueError("Shopping list not found")

    items = get_open_shopping_items(str(list_id))
    categories = sorted({item["category"] for item in items}, key=str.casefold)
    configured = load_category_orders(db).get(str(list_id), [])
    aliases = load_category_aliases(db).get(str(list_id), {})
    order = ordered_categories(categories, configured)
    index = {name.casefold(): position for position, name in enumerate(order)}
    items.sort(key=lambda item: (index.get(item["category"].casefold(), 9999), item["name"].casefold()))
    return {
        "id": str(list_id),
        "name": selected.get("name") or "Shopping list",
        "items": items,
        "count": len(items),
        "categories": categories,
        "category_order": order,
        "category_aliases": aliases,
    }
