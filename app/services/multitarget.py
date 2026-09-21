from __future__ import annotations

from app.models import BarcodeTarget, Item
from app.services.homeassistant import notify_shopping_route
from app.services.shopping import add_recipe_to_list, effective_list_ids, route_item_scan
from app.services.targets import list_ids


def _effective_route(target: BarcodeTarget, item: Item | None) -> str:
    route = (target.route or "inherit").lower()
    if route == "inherit":
        route = (item.shopping_route or "default").lower() if item else "mealie"
    if route == "default":
        route = "mealie"
    return route


def route_targets(barcode: str, targets: list[BarcodeTarget], db, *, paused: bool = False) -> dict:
    """Execute all enabled targets for one physical scan and aggregate the result."""
    results = []
    for target in targets:
        if not target.enabled:
            continue
        if target.target_type == "food":
            item = db.get(Item, target.target_id)
            if not item:
                results.append({"target": target, "ok": False, "result": "needs_mapping", "name": target.target_name or target.target_id})
                continue
            route = _effective_route(target, item)
            ids = list_ids(target)
            if paused:
                routed = {"ok": True, "via": route, "list_ids": ids, "mealie": None, "ha": None}
            else:
                routed = route_item_scan(
                    item,
                    barcode=barcode,
                    quantity=target.quantity,
                    unit_id=target.unit_id or item.default_unit_id,
                    route_override=route,
                    list_ids_override=ids,
                    db=db,
                )
            results.append({
                "target": target,
                "ok": bool(routed.get("ok")),
                "result": "added" if routed.get("ok") else "error",
                "name": item.name,
                "via": routed.get("via"),
                "list_ids": routed.get("list_ids", ids),
            })
            continue

        if target.target_type == "recipe":
            name = target.target_name or target.target_id
            route = _effective_route(target, None)
            # effective_list_ids resolves the default lazily only when this target
            # does not already contain explicit list IDs.
            ids = effective_list_ids(list_ids(target), db)
            mealie_ok = None
            ha_ok = None
            if paused:
                ok = True
            else:
                if route in {"mealie", "both"}:
                    mealie_results = [add_recipe_to_list(target.target_id, target.recipe_scale or 1.0, list_id) for list_id in ids]
                    mealie_ok = bool(mealie_results) and all(mealie_results)
                if route in {"homeassistant", "both"}:
                    ha_ok = notify_shopping_route(
                        barcode=barcode,
                        item_id=target.target_id,
                        item_name=name,
                        quantity=target.recipe_scale or 1.0,
                        unit_id=None,
                        route=route,
                    )
                if route == "none":
                    ok = True
                else:
                    required = [value for value in (mealie_ok, ha_ok) if value is not None]
                    ok = bool(required) and all(required)
            results.append({
                "target": target,
                "ok": ok,
                "result": "added" if ok else "error",
                "name": name,
                "via": route,
                "list_ids": ids,
            })
            continue

        results.append({"target": target, "ok": False, "result": "error", "name": target.target_name or target.target_id})

    if not results:
        return {"ok": False, "result": "needs_mapping", "results": [], "names": []}
    failures = [row for row in results if not row["ok"]]
    return {
        "ok": not failures,
        "result": "added" if not failures else ("partial" if len(failures) < len(results) else "error"),
        "results": results,
        "names": [row["name"] for row in results],
    }
