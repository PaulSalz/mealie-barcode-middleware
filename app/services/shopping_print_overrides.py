from __future__ import annotations

import json
from copy import deepcopy

from sqlalchemy.orm import Session

from app.models import SystemState

_ITEM_OVERRIDES_KEY = "shopping_print.item_overrides"
_MARKER_STYLE_KEY = "shopping_print.item_marker_style"
_MARKER_STYLES = {"checkbox", "dash", "none"}


def _state_json(db: Session, key: str, default):
    row = db.get(SystemState, key)
    if not row or not row.value:
        return deepcopy(default)
    try:
        return json.loads(row.value)
    except (TypeError, ValueError):
        return deepcopy(default)


def _save_state_json(db: Session, key: str, value) -> None:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    row = db.get(SystemState, key)
    if row:
        row.value = encoded
    else:
        db.add(SystemState(key=key, value=encoded))
    db.commit()


def load_marker_style(db: Session) -> str:
    raw = _state_json(db, _MARKER_STYLE_KEY, "checkbox")
    value = str(raw or "checkbox").strip().lower()
    return value if value in _MARKER_STYLES else "checkbox"


def save_marker_style(db: Session, value: str) -> str:
    value = str(value or "checkbox").strip().lower()
    if value not in _MARKER_STYLES:
        raise ValueError("item_marker_style must be checkbox, dash or none")
    _save_state_json(db, _MARKER_STYLE_KEY, value)
    return value


def item_override_key(item: dict) -> str:
    """Use the concrete Mealie shopping-list row as the override identity.

    A food can occur more than once on the same list with different quantities or
    units. Food-level keys therefore cause one override to affect several rows.
    """
    item_id = str(item.get("id") or "").strip()
    if item_id:
        return f"item:{item_id}"
    food_id = str(item.get("food_id") or "").strip()
    return f"food:{food_id}" if food_id else ""


def _quantity_value_text(item: dict) -> str:
    value = item.get("quantity")
    if value is None or value == "":
        return ""
    try:
        number = float(value)
        if number.is_integer():
            return str(int(number))
        return f"{number:.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value).strip()


def _unit_text(item: dict, quantity_value: str) -> str:
    combined = str(item.get("quantity_text") or "").strip()
    if not combined:
        return ""
    if quantity_value and combined == quantity_value:
        return ""
    if quantity_value and combined.startswith(quantity_value):
        return combined[len(quantity_value):].strip()
    return ""


def _bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on"}
    return bool(value)


def load_item_overrides(db: Session) -> dict[str, dict[str, dict]]:
    raw = _state_json(db, _ITEM_OVERRIDES_KEY, {})
    if not isinstance(raw, dict):
        return {}
    result: dict[str, dict[str, dict]] = {}
    for list_id, entries in raw.items():
        if not isinstance(entries, dict):
            continue
        clean: dict[str, dict] = {}
        for key, entry in entries.items():
            if not isinstance(entry, dict):
                continue
            override_key = str(key or "").strip()[:200]
            if not override_key:
                continue
            name_alias = str(entry.get("name_alias") or "").strip()[:160]
            quantity_alias = str(entry.get("quantity_alias") or "").strip()[:60]
            unit_alias = str(entry.get("unit_alias") or "").strip()[:60]
            hide_unit = _bool(entry.get("hide_unit", False))
            hide_quantity = _bool(entry.get("hide_quantity", False))
            if not name_alias and not quantity_alias and not unit_alias and not hide_unit and not hide_quantity:
                continue
            clean[override_key] = {
                "name_alias": name_alias,
                "quantity_alias": quantity_alias,
                "unit_alias": unit_alias,
                "hide_unit": hide_unit,
                "hide_quantity": hide_quantity,
                "source_name": str(entry.get("source_name") or "").strip()[:160],
                "source_quantity_text": str(entry.get("source_quantity_text") or "").strip()[:60],
                "source_unit_text": str(entry.get("source_unit_text") or "").strip()[:60],
            }
        result[str(list_id)] = clean
    return result


def save_item_override(
    db: Session,
    list_id: str,
    override_key: str,
    name_alias: str,
    quantity_alias: str,
    unit_alias: str = "",
    source_name: str = "",
    source_quantity_text: str = "",
    source_unit_text: str = "",
    hide_unit: bool = False,
    hide_quantity: bool = False,
) -> dict | None:
    list_id = str(list_id or "").strip()
    override_key = str(override_key or "").strip()
    name_alias = str(name_alias or "").strip()
    quantity_alias = str(quantity_alias or "").strip()
    unit_alias = str(unit_alias or "").strip()
    source_name = str(source_name or "").strip()
    source_quantity_text = str(source_quantity_text or "").strip()
    source_unit_text = str(source_unit_text or "").strip()
    hide_unit = _bool(hide_unit)
    hide_quantity = _bool(hide_quantity)
    if not list_id or not override_key:
        raise ValueError("Shopping list id and item key are required")
    if len(override_key) > 200 or len(name_alias) > 160 or len(source_name) > 160:
        raise ValueError("Item override name is too long")
    if (
        len(quantity_alias) > 60
        or len(unit_alias) > 60
        or len(source_quantity_text) > 60
        or len(source_unit_text) > 60
    ):
        raise ValueError("Item override quantity or unit is too long")

    all_rows = load_item_overrides(db)
    rows = dict(all_rows.get(list_id, {}))
    if not name_alias and not quantity_alias and not unit_alias and not hide_unit and not hide_quantity:
        rows.pop(override_key, None)
        saved = None
    else:
        saved = {
            "name_alias": name_alias,
            "quantity_alias": quantity_alias,
            "unit_alias": unit_alias,
            "hide_unit": hide_unit,
            "hide_quantity": hide_quantity,
            "source_name": source_name,
            "source_quantity_text": source_quantity_text,
            "source_unit_text": source_unit_text,
        }
        rows[override_key] = saved
    all_rows[list_id] = rows
    _save_state_json(db, _ITEM_OVERRIDES_KEY, all_rows)
    return saved


def delete_item_override(db: Session, list_id: str, override_key: str) -> None:
    save_item_override(db, list_id, override_key, "", "", "")


def apply_item_overrides(db: Session, list_id: str, payload: dict) -> dict:
    list_id = str(list_id)
    overrides = load_item_overrides(db).get(list_id, {})
    active_keys: set[str] = set()

    # Legacy food-level overrides are only safe when that food appears once.
    food_counts: dict[str, int] = {}
    for item in payload.get("items") or []:
        if isinstance(item, dict):
            food_id = str(item.get("food_id") or "").strip()
            if food_id:
                food_counts[food_id] = food_counts.get(food_id, 0) + 1

    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        key = item_override_key(item)
        original_name = str(item.get("name") or "")
        original_quantity_text = str(item.get("quantity_text") or "")
        quantity_value = _quantity_value_text(item)
        unit_value = _unit_text(item, quantity_value)
        item["override_key"] = key
        item["original_name"] = original_name
        item["original_quantity_text"] = original_quantity_text
        item["original_quantity_value_text"] = quantity_value
        item["original_unit_text"] = unit_value

        override = overrides.get(key) if key else None
        active_key = key
        if not override:
            food_id = str(item.get("food_id") or "").strip()
            legacy_key = f"food:{food_id}" if food_id else ""
            if legacy_key and food_counts.get(food_id) == 1 and legacy_key in overrides:
                override = overrides[legacy_key]
                active_key = legacy_key

        if override:
            active_keys.add(active_key)
            if override.get("name_alias"):
                item["name"] = override["name_alias"]
            if _bool(override.get("hide_quantity", False)):
                quantity_display = ""
                unit_display = ""
            else:
                quantity_display = str(override.get("quantity_alias") or quantity_value).strip()
                if _bool(override.get("hide_unit", False)):
                    unit_display = ""
                else:
                    unit_display = str(override.get("unit_alias") or unit_value).strip()
            item["quantity_text"] = " ".join(part for part in (quantity_display, unit_display) if part).strip()

    payload["item_overrides"] = [
        {
            "key": key,
            "name_alias": entry.get("name_alias") or "",
            "quantity_alias": entry.get("quantity_alias") or "",
            "unit_alias": entry.get("unit_alias") or "",
            "hide_unit": _bool(entry.get("hide_unit", False)),
            "hide_quantity": _bool(entry.get("hide_quantity", False)),
            "source_name": entry.get("source_name") or key,
            "source_quantity_text": entry.get("source_quantity_text") or "",
            "source_unit_text": entry.get("source_unit_text") or "",
            "active": key in active_keys,
        }
        for key, entry in sorted(
            overrides.items(),
            key=lambda pair: (str(pair[1].get("source_name") or pair[0]).casefold(), pair[0]),
        )
    ]
    return payload
