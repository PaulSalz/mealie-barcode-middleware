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
    food_id = str(item.get("food_id") or "").strip()
    if food_id:
        return f"food:{food_id}"
    item_id = str(item.get("id") or "").strip()
    return f"item:{item_id}" if item_id else ""


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
            if not name_alias and not quantity_alias:
                continue
            clean[override_key] = {
                "name_alias": name_alias,
                "quantity_alias": quantity_alias,
                "source_name": str(entry.get("source_name") or "").strip()[:160],
                "source_quantity_text": str(entry.get("source_quantity_text") or "").strip()[:60],
            }
        result[str(list_id)] = clean
    return result


def save_item_override(
    db: Session,
    list_id: str,
    override_key: str,
    name_alias: str,
    quantity_alias: str,
    source_name: str = "",
    source_quantity_text: str = "",
) -> dict | None:
    list_id = str(list_id or "").strip()
    override_key = str(override_key or "").strip()
    name_alias = str(name_alias or "").strip()
    quantity_alias = str(quantity_alias or "").strip()
    source_name = str(source_name or "").strip()
    source_quantity_text = str(source_quantity_text or "").strip()
    if not list_id or not override_key:
        raise ValueError("Shopping list id and item key are required")
    if len(override_key) > 200 or len(name_alias) > 160 or len(source_name) > 160:
        raise ValueError("Item override name is too long")
    if len(quantity_alias) > 60 or len(source_quantity_text) > 60:
        raise ValueError("Item override quantity is too long")

    all_rows = load_item_overrides(db)
    rows = dict(all_rows.get(list_id, {}))
    if not name_alias and not quantity_alias:
        rows.pop(override_key, None)
        saved = None
    else:
        saved = {
            "name_alias": name_alias,
            "quantity_alias": quantity_alias,
            "source_name": source_name,
            "source_quantity_text": source_quantity_text,
        }
        rows[override_key] = saved
    all_rows[list_id] = rows
    _save_state_json(db, _ITEM_OVERRIDES_KEY, all_rows)
    return saved


def delete_item_override(db: Session, list_id: str, override_key: str) -> None:
    save_item_override(db, list_id, override_key, "", "")


def apply_item_overrides(db: Session, list_id: str, payload: dict) -> dict:
    list_id = str(list_id)
    overrides = load_item_overrides(db).get(list_id, {})
    active_keys: set[str] = set()

    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        key = item_override_key(item)
        original_name = str(item.get("name") or "")
        original_quantity = str(item.get("quantity_text") or "")
        item["override_key"] = key
        item["original_name"] = original_name
        item["original_quantity_text"] = original_quantity
        override = overrides.get(key) if key else None
        if override:
            active_keys.add(key)
            if override.get("name_alias"):
                item["name"] = override["name_alias"]
            if override.get("quantity_alias"):
                item["quantity_text"] = override["quantity_alias"]

    payload["item_overrides"] = [
        {
            "key": key,
            "name_alias": entry.get("name_alias") or "",
            "quantity_alias": entry.get("quantity_alias") or "",
            "source_name": entry.get("source_name") or key,
            "source_quantity_text": entry.get("source_quantity_text") or "",
            "active": key in active_keys,
        }
        for key, entry in sorted(
            overrides.items(),
            key=lambda pair: (str(pair[1].get("source_name") or pair[0]).casefold(), pair[0]),
        )
    ]
    return payload
