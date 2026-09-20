import json
import logging
from datetime import timedelta, timezone
from urllib.parse import quote, unquote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_token
from app.config import settings
from app.database import get_db
from app.events import scan_events
from app.models import Activity, BarcodeCache, BarcodeMapping, Item
from app.pause import is_paused
from app.services.actions import execute_action, find_action
from app.services.barcode_lookup import enrich_barcode_background, needs_background_enrich, perform_lookup
from app.services.barcode_routing import dispatch_barcode_targets
from app.services.fuzzy import try_auto_map
from app.services.homeassistant import notify_scan as ha_notify_scan, should_send_scan_webhook
from app.services.mealie import add_shopping_note, enqueue_retry
from app.services.shopping import add_recipe_to_list, get_default_shopping_list_id, route_item_scan
from app.services.targets import get_barcode_targets
from app.utils import utcnow

logger = logging.getLogger(__name__)
router = APIRouter()


def _build_action_url(barcode: str) -> str:
    encoded = quote(barcode, safe="")
    base = settings.middleware_base_url.rstrip("/")
    return f"{base}/barcodes/{encoded}" if base else f"/barcodes/{encoded}"


def _build_action_detail_url(action_id: str) -> str:
    encoded = quote(action_id, safe="")
    base = settings.middleware_base_url.rstrip("/")
    return f"{base}/actions/{encoded}" if base else f"/actions/{encoded}"


class ScanRequest(BaseModel):
    barcode: str = Field(..., max_length=256)


class ScanResponse(BaseModel):
    result: str
    item: str | None = None
    via: str | None = None
    needs_action: bool = False
    action_url: str | None = None
    brand: str | None = None
    quantity: str | None = None
    item_source: str | None = None
    paused: bool = False
    target_count: int | None = None


def _queue_ha_notification(resp: ScanResponse, barcode: str, background_tasks: BackgroundTasks) -> None:
    if not should_send_scan_webhook(resp.result, resp.needs_action):
        return
    added_to_list = (
        resp.via is not None
        and resp.result not in {"unknown", "unknown_action", "needs_mapping", "error"}
        and not resp.paused
    )
    background_tasks.add_task(
        ha_notify_scan,
        barcode,
        resp.item,
        resp.result,
        resp.action_url or _build_action_url(barcode),
        added_to_list,
        resp.paused,
    )


def _scan_failure(barcode: str, db: Session, background_tasks: BackgroundTasks) -> ScanResponse:
    db.rollback()
    try:
        _save_activity(barcode, "Scan failed", barcode, "error", db)
    except Exception:
        db.rollback()
    resp = ScanResponse(
        result="error",
        item=barcode,
        needs_action=True,
        action_url=_build_action_url(barcode),
    )
    _queue_ha_notification(resp, barcode, background_tasks)
    return resp


@router.post("/scan", response_model=ScanResponse)
def scan_barcode(
    body: ScanRequest,
    background_tasks: BackgroundTasks,
    _token=Depends(require_token),
    db: Session = Depends(get_db),
):
    barcode = body.barcode.strip()
    if not barcode:
        raise HTTPException(status_code=422, detail="Barcode cannot be empty")
    try:
        resp = _process_scan(barcode, db, background_tasks)
        _queue_ha_notification(resp, barcode, background_tasks)
        return resp
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error processing scan for barcode %s", barcode)
        return _scan_failure(barcode, db, background_tasks)


def _ensure_action_cache(barcode: str, action, db: Session) -> BarcodeCache:
    cached = db.get(BarcodeCache, barcode)
    now = utcnow()
    if not cached:
        cached = BarcodeCache(
            barcode=barcode,
            source="action",
            title=action.name,
            found=True,
            lookup_attempted_at=now,
            created_at=now,
        )
        db.add(cached)
        db.commit()
    elif cached.source == "action" and not cached.custom_title:
        cached.title = action.name
        cached.found = True
        cached.lookup_attempted_at = now
        db.commit()
    return cached


def _process_action_code(barcode: str, db: Session, background_tasks: BackgroundTasks, paused: bool) -> ScanResponse:
    action_id = barcode[len("ACTION:"):].strip()
    action = find_action(db, action_id) if action_id else None
    if not action:
        resp = ScanResponse(
            result="unknown_action",
            item=action_id or barcode,
            needs_action=True,
            action_url=(settings.middleware_base_url.rstrip("/") + "/actions") if settings.middleware_base_url else "/actions",
            item_source="action",
            paused=paused,
        )
        _save_activity(
            barcode, "Unknown action", action_id or barcode, resp.result, db,
            target_type="action", target_id=action_id or None, target_name=action_id or None,
        )
        _save_notification(barcode, "Unknown action", f"No action exists for {action_id or barcode}", "unknown_action", db)
        _emit_scan_event(barcode, resp)
        return resp

    _ensure_action_cache(barcode, action, db)
    action_url = _build_action_detail_url(action.id)
    if paused and action.respect_pause:
        resp = ScanResponse(
            result="action_paused", item=action.name, paused=True,
            item_source="action", action_url=action_url,
        )
        _save_activity(
            barcode, "Action skipped (scan & link)", action.name, resp.result, db,
            target_type="action", target_id=action.id, target_name=action.name,
        )
        _emit_scan_event(barcode, resp)
        return resp

    if action.execution_mode == "async":
        background_tasks.add_task(execute_action, action.id, barcode)
        resp = ScanResponse(
            result="action_queued", item=action.name, via="action",
            item_source="action", action_url=action_url,
        )
        _save_activity(
            barcode, "Action queued", action.name, resp.result, db,
            target_type="action", target_id=action.id, target_name=action.name,
        )
        _emit_scan_event(barcode, resp)
        return resp

    result = execute_action(action.id, barcode)
    status = result.get("status")
    if status == "success":
        response_result, needs_action = "action_triggered", False
    elif status == "ignored_cooldown":
        response_result, needs_action = "action_ignored", False
    elif status == "disabled":
        response_result, needs_action = "action_disabled", True
    else:
        response_result, needs_action = "error", True

    resp = ScanResponse(
        result=response_result,
        item=action.name,
        via="action" if status in {"success", "ignored_cooldown"} else None,
        item_source="action",
        needs_action=needs_action,
        action_url=action_url,
    )
    _save_activity(
        barcode,
        "Action triggered" if status == "success" else "Action scan",
        action.name,
        response_result,
        db,
        target_type="action", target_id=action.id, target_name=action.name,
    )
    if needs_action:
        _save_notification(barcode, "Action failed", f"{action.name}: {result.get('error') or status}", "error", db)
    _emit_scan_event(barcode, resp)
    return resp


def _process_multi_targets(barcode: str, db: Session, paused: bool) -> ScanResponse | None:
    targets = get_barcode_targets(db, barcode)
    if not targets:
        return None
    cached = db.get(BarcodeCache, barcode)
    routed = dispatch_barcode_targets(db, barcode, targets, paused=paused)
    resp = ScanResponse(
        result=routed["result"],
        item=routed["item"],
        via=routed.get("via"),
        needs_action=bool(routed.get("needs_action")),
        action_url=_build_action_url(barcode) if routed.get("needs_action") else None,
        brand=cached.display_brand if cached else None,
        quantity=cached.quantity if cached else None,
        paused=paused,
        target_count=routed.get("target_count") or len(targets),
    )
    if len(targets) == 1:
        target = targets[0]
        target_type = target.target_type
        target_id = target.target_id
        target_name = target.target_name
    else:
        target_type = "multi"
        target_id = None
        target_name = routed["item"]
    title = "Scanned (scan & link)" if paused else {
        "added": "Added to destinations",
        "queued": "Queued for retry",
        "partial": "Partially routed",
        "error": "Routing failed",
    }.get(resp.result, "Barcode routed")
    _save_activity(
        barcode, title, routed["item"], resp.result, db,
        target_type=target_type, target_id=target_id, target_name=target_name,
    )
    if resp.needs_action:
        _save_notification(barcode, title, routed["item"], resp.result, db)
    _emit_scan_event(barcode, resp)
    return resp


def _process_mapped(barcode: str, mapping: BarcodeMapping, db: Session, paused: bool) -> ScanResponse:
    """Legacy fallback for installations before BarcodeTarget backfill."""
    cached = db.get(BarcodeCache, barcode)
    if mapping.target_type == "recipe":
        recipe_name = mapping.target_name or f"Recipe {mapping.target_id}"
        if paused:
            resp = ScanResponse(result="added", item=recipe_name, paused=True, item_source="recipe")
        else:
            list_id = mapping.shopping_list_id or get_default_shopping_list_id()
            success = add_recipe_to_list(mapping.target_id, mapping.recipe_scale or 1.0, list_id)
            resp = ScanResponse(
                result="added" if success else "error",
                item=recipe_name,
                via="recipe" if success else None,
                item_source="recipe",
                needs_action=not success,
                action_url=_build_action_url(barcode) if not success else None,
            )
        _save_activity(
            barcode,
            "Scanned (scan & link)" if paused else ("Added recipe to list" if resp.result == "added" else "Recipe add failed"),
            recipe_name, resp.result, db, mapping=mapping,
        )
        _emit_scan_event(barcode, resp)
        return resp

    item = db.get(Item, mapping.target_id)
    item_name = item.name if item else (mapping.target_name or barcode)
    if not item:
        resp = ScanResponse(result="needs_mapping", item=item_name, needs_action=True, action_url=_build_action_url(barcode))
        _save_activity(barcode, "Broken Food mapping", item_name, resp.result, db, mapping=mapping)
        _save_notification(barcode, "Broken Food mapping", f"{item_name} no longer exists in the local Mealie Food cache", "needs_mapping", db)
        _emit_scan_event(barcode, resp)
        return resp

    if paused:
        resp = ScanResponse(
            result="added", item=item_name, paused=True,
            brand=cached.display_brand if cached else None,
            quantity=cached.quantity if cached else None,
            item_source=item.source,
        )
    else:
        resp = _add_via_item(item, item_name, barcode, db, cached=cached, mapping=mapping)
    _save_activity(
        barcode,
        "Scanned (scan & link)" if paused else (
            "Added to destination" if resp.result == "added" else "Queued" if resp.result == "queued" else "Routing failed"
        ),
        item_name, resp.result, db, mapping=mapping,
    )
    _emit_scan_event(barcode, resp)
    return resp


def _process_scan(barcode: str, db: Session, background_tasks: BackgroundTasks) -> ScanResponse:
    paused = is_paused(db)

    # ACTION: is a reserved namespace and keeps its action semantics.
    if barcode.upper().startswith("ACTION:"):
        return _process_action_code(barcode, db, background_tasks, paused)

    multi = _process_multi_targets(barcode, db, paused)
    if multi:
        return multi

    mapping = db.get(BarcodeMapping, barcode)
    if mapping:
        return _process_mapped(barcode, mapping, db, paused)

    if barcode.upper().startswith("GENERIC:"):
        term = unquote(barcode[len("GENERIC:"):].strip())
        resp = _handle_generic(term, barcode, db, paused=paused)
        current_mapping = db.get(BarcodeMapping, barcode)
        _save_activity(
            barcode,
            "Scanned (scan & link)" if paused else (
                "Added to destination" if resp.result == "added" else "Queued" if resp.result == "queued" else "Generic scan"
            ),
            resp.item or term or barcode,
            resp.result,
            db,
            mapping=current_mapping,
        )
        _emit_scan_event(barcode, resp)
        return resp

    cached = db.get(BarcodeCache, barcode)

    # Product databases are numeric-barcode oriented. Arbitrary keyboard/HID codes
    # are still valid scanner inputs; create a local unresolved cache entry instead
    # of rejecting them with HTTP 422.
    if not barcode.isdigit() and cached is None:
        cached = BarcodeCache(
            barcode=barcode,
            source="custom",
            title=barcode,
            found=False,
            lookup_attempted_at=utcnow(),
            created_at=utcnow(),
        )
        db.add(cached)
        db.commit()

    needs_lookup = cached is None and barcode.isdigit()
    if cached is not None and not cached.found and cached.lookup_attempted_at:
        attempted = cached.lookup_attempted_at
        if attempted.tzinfo is None:
            attempted = attempted.replace(tzinfo=timezone.utc)
        if barcode.isdigit() and utcnow() > attempted + timedelta(days=settings.lookup_ttl_days):
            needs_lookup = True

    if needs_lookup:
        cached = perform_lookup(barcode, db)
    if needs_lookup and needs_background_enrich(cached):
        background_tasks.add_task(enrich_barcode_background, barcode)

    if not cached:
        cached = BarcodeCache(
            barcode=barcode, source="custom", title=barcode, found=False,
            lookup_attempted_at=utcnow(), created_at=utcnow(),
        )
        db.add(cached)
        db.commit()

    if not cached.found:
        if paused or settings.unknown_barcode_action == "notify_only":
            resp = ScanResponse(result="unknown", item=barcode, paused=paused)
        else:
            success, shopping_item_id = add_shopping_note(barcode)
            if success and shopping_item_id:
                cached.shopping_item_id = shopping_item_id
                db.commit()
            elif not success:
                _enqueue_note(barcode, barcode, db)
            resp = ScanResponse(result="unknown", item=barcode, via="note")
        resp.needs_action = True
        resp.action_url = _build_action_url(barcode)
        _save_activity(barcode, "Unknown barcode (scan & link)" if paused else "Unknown barcode", barcode, "unknown", db)
        _save_notification(barcode, "Unknown barcode (scan & link)" if paused else "Unknown barcode", "Not found in any product database", "unknown", db)
        _emit_scan_event(barcode, resp)
        return resp

    display_title = cached.display_title or barcode
    display_brand = cached.display_brand
    item_id = try_auto_map(barcode, display_title, display_brand, db)
    if item_id:
        item = db.get(Item, item_id)
        item_name = item.name if item else display_title
        mapping = db.get(BarcodeMapping, barcode)
        if paused:
            resp = ScanResponse(
                result="added", item=item_name, paused=True,
                brand=display_brand, quantity=cached.quantity,
                item_source=item.source if item else None,
                needs_action=True, action_url=_build_action_url(barcode),
            )
        else:
            resp = _add_via_item(item, item_name, barcode, db, cached=cached, mapping=mapping)
            resp.needs_action = True
            resp.action_url = _build_action_url(barcode)
        _save_activity(barcode, "Scanned (scan & link)" if paused else "Added to destination", item_name, resp.result, db, mapping=mapping)
        _save_notification(barcode, "Auto-linked — review", f"{display_title} → {item_name}", "auto_mapped", db)
        _emit_scan_event(barcode, resp)
        return resp

    note = display_title
    if paused or settings.unknown_barcode_action == "notify_only":
        resp = ScanResponse(
            result="needs_mapping", item=note, paused=paused,
            brand=display_brand, quantity=cached.quantity,
            needs_action=True, action_url=_build_action_url(barcode),
        )
        _save_activity(barcode, "Not linked (scan & link)" if paused else "Not linked", note, "needs_mapping", db)
        _save_notification(barcode, "Not linked", f"{note} — tap to link to a Mealie Food or recipe", "needs_mapping", db)
    else:
        success, shopping_item_id = add_shopping_note(note)
        if success:
            if shopping_item_id:
                cached.shopping_item_id = shopping_item_id
                db.commit()
            resp = ScanResponse(
                result="added_as_note", item=note, via="note",
                brand=display_brand, quantity=cached.quantity,
                needs_action=True, action_url=_build_action_url(barcode),
            )
            _save_activity(barcode, "Added to list", note + " (via note)", "added_as_note", db)
            _save_notification(barcode, "Not linked", f"{note} — tap to link to a Mealie Food or recipe", "needs_mapping", db)
        else:
            _enqueue_note(barcode, note, db)
            resp = ScanResponse(
                result="queued", item=note, via="note",
                brand=display_brand, quantity=cached.quantity,
                needs_action=True, action_url=_build_action_url(barcode),
            )
            _save_activity(barcode, "Queued", note, "queued", db)
    _emit_scan_event(barcode, resp)
    return resp


def _emit_scan_event(barcode: str, resp: ScanResponse):
    scan_events.publish_threadsafe("scan", {
        "barcode": barcode,
        "result": resp.result,
        "item": resp.item,
        "paused": resp.paused,
        "target_count": resp.target_count,
    })


def _save_notification(barcode: str, title: str, message: str, result: str, db: Session):
    existing = db.query(Activity).filter(Activity.barcode == barcode, Activity.is_read == False).first()
    if existing:
        return
    db.add(Activity(barcode=barcode, title=title, message=message, result=result))
    db.commit()


def _save_activity(
    barcode: str,
    title: str,
    message: str,
    result: str,
    db: Session,
    *,
    mapping: BarcodeMapping | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    target_name: str | None = None,
):
    if mapping:
        target_type = mapping.target_type
        target_id = mapping.target_id
        target_name = mapping.target_name
    db.add(Activity(
        barcode=barcode,
        title=title,
        message=message,
        result=result,
        is_read=True,
        is_dismissed=True,
        is_scan_event=True,
        target_type=target_type,
        target_id=target_id,
        target_name=target_name,
        quantity_snapshot=(mapping.quantity if mapping and mapping.target_type == "food" else None),
        unit_id_snapshot=(mapping.unit_id if mapping and mapping.target_type == "food" else None),
        recipe_scale_snapshot=(mapping.recipe_scale if mapping and mapping.target_type == "recipe" else None),
    ))
    db.commit()


def _handle_generic(term: str, barcode: str, db: Session, paused: bool = False) -> ScanResponse:
    from rapidfuzz import fuzz

    if not term:
        return ScanResponse(result="unknown", item=None)

    cached = db.get(BarcodeCache, barcode)
    if not cached:
        cached = BarcodeCache(
            barcode=barcode,
            source="generic",
            title=term,
            found=True,
            lookup_attempted_at=utcnow(),
            created_at=utcnow(),
        )
        db.add(cached)
        db.commit()

    best_score = 0
    best_item = None
    for item in db.query(Item).filter(Item.source == "mealie").all():
        score = fuzz.token_sort_ratio(term.lower(), item.name.lower())
        if item.aliases:
            try:
                for alias in json.loads(item.aliases):
                    score = max(score, fuzz.token_sort_ratio(term.lower(), alias.lower()))
            except (json.JSONDecodeError, TypeError):
                pass
        if score > best_score:
            best_score = score
            best_item = item

    if best_item and best_score >= settings.fuzzy_match_threshold:
        mapping = BarcodeMapping(
            barcode=barcode,
            target_type="food",
            target_id=best_item.id,
            target_name=best_item.name,
            quantity=1.0,
            unit_id=None,
            recipe_scale=1.0,
            mapped_by="generic",
        )
        db.add(mapping)
        db.commit()
        if paused:
            return ScanResponse(result="added", item=best_item.name, paused=True, item_source=best_item.source)
        return _add_via_item(best_item, best_item.name, barcode, db, cached=cached, mapping=mapping)

    if paused:
        return ScanResponse(result="added_as_note", item=term, paused=True)

    success, shopping_item_id = add_shopping_note(term)
    if success:
        if shopping_item_id:
            cached.shopping_item_id = shopping_item_id
            db.commit()
        return ScanResponse(result="added_as_note", item=term, via="note")
    _enqueue_note(barcode, term, db)
    return ScanResponse(result="queued", item=term, via="note")


def _add_via_item(
    item: Item | None,
    item_name: str,
    barcode: str,
    db: Session,
    cached: BarcodeCache | None = None,
    mapping: BarcodeMapping | None = None,
) -> ScanResponse:
    brand = cached.display_brand if cached else None
    package_quantity = cached.quantity if cached else None
    item_source = item.source if item else None
    if not item:
        return ScanResponse(
            result="needs_mapping", item=item_name,
            brand=brand, quantity=package_quantity,
            needs_action=True, action_url=_build_action_url(barcode),
        )

    list_quantity = mapping.quantity if mapping else 1.0
    unit_id = mapping.unit_id if mapping else None
    routed = route_item_scan(
        item,
        barcode=barcode,
        quantity=list_quantity,
        unit_id=unit_id,
    )
    if routed["ok"]:
        return ScanResponse(
            result="added", item=item_name, via=routed["via"],
            brand=brand, quantity=package_quantity, item_source=item_source,
        )

    # Mealie failures remain retryable. HA/webhook failures are surfaced immediately
    # because repeating arbitrary automations later may not be idempotent.
    if routed.get("mealie") is False:
        if item.source == "mealie":
            payload = {
                "shoppingListId": routed["list_id"],
                "foodId": item.id,
            }
            if list_quantity is not None and list_quantity > 0.001:
                payload["quantity"] = list_quantity
            if unit_id:
                payload["unitId"] = unit_id
        else:
            payload = {"shoppingListId": routed["list_id"], "note": item.name, "quantity": 1}
        enqueue_retry(barcode, payload, db)
        if routed.get("ha") is not False:
            return ScanResponse(
                result="queued", item=item_name, via=routed["via"],
                brand=brand, quantity=package_quantity, item_source=item_source,
            )

    return ScanResponse(
        result="error", item=item_name,
        brand=brand, quantity=package_quantity, item_source=item_source,
        needs_action=True, action_url=_build_action_url(barcode),
    )


def _enqueue_note(barcode: str, note: str, db: Session) -> None:
    list_id = get_default_shopping_list_id()
    enqueue_retry(barcode, {"shoppingListId": list_id, "note": note}, db)


class AppScanRequest(BaseModel):
    content: str = Field(..., max_length=256)
    deviceId: str = Field(..., max_length=256)
    model_config = {"extra": "ignore"}


@router.post("/scan/app", response_model=ScanResponse)
def scan_barcode_app(body: AppScanRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    from app.auth import verify_psk

    verify_psk(body.deviceId, db)
    barcode = body.content.strip()
    if not barcode:
        raise HTTPException(status_code=422, detail="Barcode cannot be empty")
    try:
        resp = _process_scan(barcode, db, background_tasks)
        _queue_ha_notification(resp, barcode, background_tasks)
        return resp
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error processing app scan for barcode %s", barcode)
        return _scan_failure(barcode, db, background_tasks)
