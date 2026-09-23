from __future__ import annotations

import logging
import time
from concurrent.futures import as_completed
from types import SimpleNamespace

from app.models import BarcodeTarget, Item
from app.services.bounded_executor import BoundedExecutor
from app.services.homeassistant import notify_shopping_route
from app.services.shopping import add_recipe_to_list, effective_list_ids, route_item_scan
from app.services.targets import list_ids

logger = logging.getLogger(__name__)
_ROUTE_POOL = BoundedExecutor(max_workers=8, max_pending=32, thread_name_prefix="target-route")
_SUBROUTE_POOL = BoundedExecutor(max_workers=12, max_pending=64, thread_name_prefix="target-subroute")


def _effective_route(target: BarcodeTarget, item: Item | None) -> str:
    route = (target.route or "inherit").lower()
    if route == "inherit":
        route = (item.shopping_route or "default").lower() if item else "mealie"
    if route == "default":
        route = "mealie"
    return route


def _food_snapshot(item: Item):
    """Detach the fields needed by the worker from the SQLAlchemy session."""
    return SimpleNamespace(
        id=item.id,
        name=item.name,
        source=item.source,
        shopping_route=item.shopping_route,
        shopping_list_id=item.shopping_list_id,
    )


def _route_food(plan: dict) -> dict:
    started = time.monotonic()
    item = plan["item"]
    route = plan["route"]
    if route == "none":
        routed = {
            "ok": True,
            "via": "none",
            "list_ids": plan["list_ids"],
            "mealie": None,
            "ha": None,
        }
    else:
        routed = route_item_scan(
            item,
            barcode=plan["barcode"],
            quantity=plan["quantity"],
            unit_id=plan["unit_id"],
            route_override=route,
            list_ids_override=plan["list_ids"],
            # Never share the request Session across worker threads. Explicit
            # list IDs avoid DB work; if a fallback is still required the
            # shopping helper opens its own short-lived Session.
            db=None,
        )
    duration_ms = int((time.monotonic() - started) * 1000)
    if duration_ms >= 1000:
        logger.warning(
            "Slow Food target route: barcode=%s target=%s took %d ms via=%s",
            plan["barcode"], plan["target_id"], duration_ms, route,
        )
    return {
        "ok": bool(routed.get("ok")),
        "result": "added" if routed.get("ok") else "error",
        "name": item.name,
        "via": routed.get("via"),
        "list_ids": routed.get("list_ids", plan["list_ids"]),
        "duration_ms": duration_ms,
    }


def _route_recipe(plan: dict) -> dict:
    """Route one Recipe target.

    A recipe can fan out to several Mealie shopping lists plus Home Assistant.
    Those network operations are independent, so execute them concurrently while
    retaining synchronous success semantics for the caller.
    """
    started = time.monotonic()
    route = plan["route"]
    ids = plan["list_ids"]
    mealie_ok = None
    ha_ok = None

    mealie_futures = []
    ha_future = None
    if route in {"mealie", "both"}:
        mealie_futures = [
            _SUBROUTE_POOL.submit(
                add_recipe_to_list,
                plan["target_id"],
                plan["scale"],
                list_id,
                block=True,
            )
            for list_id in ids
        ]
    if route in {"homeassistant", "both"}:
        ha_future = _SUBROUTE_POOL.submit(
            notify_shopping_route,
            barcode=plan["barcode"],
            item_id=plan["target_id"],
            item_name=plan["name"],
            quantity=plan["scale"],
            unit_id=None,
            route=route,
            block=True,
        )

    if route in {"mealie", "both"}:
        mealie_results = [future.result() for future in mealie_futures]
        mealie_ok = bool(mealie_results) and all(mealie_results)
    if ha_future is not None:
        ha_ok = bool(ha_future.result())

    if route == "none":
        ok = True
    else:
        required = [value for value in (mealie_ok, ha_ok) if value is not None]
        ok = bool(required) and all(required)

    duration_ms = int((time.monotonic() - started) * 1000)
    if duration_ms >= 1000:
        logger.warning(
            "Slow Recipe target route: barcode=%s target=%s took %d ms via=%s lists=%d",
            plan["barcode"], plan["target_id"], duration_ms, route, len(ids),
        )
    return {
        "ok": ok,
        "result": "added" if ok else "error",
        "name": plan["name"],
        "via": route,
        "list_ids": ids,
        "duration_ms": duration_ms,
    }


def route_targets(barcode: str, targets: list[BarcodeTarget], db, *, paused: bool = False) -> dict:
    """Execute enabled targets and aggregate results.

    DB-backed target resolution happens on the request thread. Independent
    network routes then run concurrently so several slow Mealie/HA targets cost
    roughly the slowest target latency instead of the sum of all target latencies.
    The worker queues are bounded; internal routing waits for a slot rather than
    retaining an unbounded number of callables in memory.
    """
    slots: list[dict | None] = []
    jobs: list[tuple[int, BarcodeTarget, dict, object]] = []

    for target in targets:
        if not target.enabled:
            continue

        slot_index = len(slots)
        slots.append(None)

        if target.target_type == "food":
            item = db.get(Item, target.target_id)
            if not item:
                slots[slot_index] = {
                    "target": target,
                    "ok": False,
                    "result": "needs_mapping",
                    "name": target.target_name or target.target_id,
                    "duration_ms": 0,
                }
                continue
            route = _effective_route(target, item)
            ids = list_ids(target)
            if paused:
                slots[slot_index] = {
                    "target": target,
                    "ok": True,
                    "result": "added",
                    "name": item.name,
                    "via": route,
                    "list_ids": ids,
                    "duration_ms": 0,
                }
                continue
            plan = {
                "barcode": barcode,
                "target_id": target.id,
                "item": _food_snapshot(item),
                "route": route,
                "list_ids": ids,
                "quantity": target.quantity,
                "unit_id": target.unit_id or item.default_unit_id,
            }
            future = _ROUTE_POOL.submit(_route_food, plan, block=True)
            jobs.append((slot_index, target, plan, future))
            continue

        if target.target_type == "recipe":
            name = target.target_name or target.target_id
            route = _effective_route(target, None)
            ids = effective_list_ids(list_ids(target), db)
            if paused:
                slots[slot_index] = {
                    "target": target,
                    "ok": True,
                    "result": "added",
                    "name": name,
                    "via": route,
                    "list_ids": ids,
                    "duration_ms": 0,
                }
                continue
            plan = {
                "barcode": barcode,
                "target_id": target.target_id,
                "name": name,
                "route": route,
                "list_ids": ids,
                "scale": target.recipe_scale or 1.0,
            }
            future = _ROUTE_POOL.submit(_route_recipe, plan, block=True)
            jobs.append((slot_index, target, plan, future))
            continue

        slots[slot_index] = {
            "target": target,
            "ok": False,
            "result": "error",
            "name": target.target_name or target.target_id,
            "duration_ms": 0,
        }

    future_map = {future: (index, target, plan) for index, target, plan, future in jobs}
    for future in as_completed(future_map):
        index, target, plan = future_map[future]
        try:
            row = future.result()
        except Exception as exc:
            logger.exception(
                "Target route failed unexpectedly: barcode=%s target=%s",
                barcode, getattr(target, "id", None),
            )
            row = {
                "ok": False,
                "result": "error",
                "name": plan.get("name") or getattr(plan.get("item"), "name", None) or target.target_name or target.target_id,
                "via": plan.get("route"),
                "list_ids": plan.get("list_ids") or [],
                "duration_ms": 0,
                "error": str(exc),
            }
        row["target"] = target
        slots[index] = row

    results = [row for row in slots if row is not None]
    if not results:
        return {"ok": False, "result": "needs_mapping", "results": [], "names": []}
    failures = [row for row in results if not row["ok"]]
    return {
        "ok": not failures,
        "result": "added" if not failures else ("partial" if len(failures) < len(results) else "error"),
        "results": results,
        "names": [row["name"] for row in results],
    }
