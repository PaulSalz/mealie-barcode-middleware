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
from app.models import Activity, BarcodeCache, BarcodeTarget, Item
from app.pause import is_paused
from app.services.actions import execute_action, find_action
from app.services.barcode_lookup import enrich_barcode_background, needs_background_enrich, perform_lookup
from app.services.fuzzy import try_auto_map
from app.services.homeassistant import notify_scan as ha_notify_scan, should_send_scan_webhook
from app.services.mealie import add_shopping_note, enqueue_retry
from app.services.multitarget import route_targets
from app.services.shopping import get_default_shopping_list_id
from app.services.targets import add_target, ensure_targets
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


def _queue_ha_notification(resp: ScanResponse, barcode: str, background_tasks: BackgroundTasks) -> None:
    if not should_send_scan_webhook(resp.result, resp.needs_action):
        return
    added_to_list = (
        resp.via is not None
        and resp.result not in {"unknown", "unknown_action", "needs_mapping", "error", "partial"}
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
    resp = ScanResponse(result="error", item=barcode, needs_action=True, action_url=_build_action_url(barcode))
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
        target_type="action",
        target_id=action.id,
        target_name=action.name,
    )
    if needs_action:
        _save_notification(barcode, "Action failed", f"{action.name}: {result.get('error') or status}", "error", db)
    _emit_scan_event(barcode, resp)
    return resp


def _target_snapshot(target: BarcodeTarget) -> dict:
    try:
        list_ids = json.loads(target.shopping_list_ids_json or "[]")
    except (TypeError, ValueError):
        list_ids = []
    return {
        "type": target.target_type,
        "id": target.target_id,
        "name": target.target_name,
        "quantity": target.quantity,
        "unit_id": target.unit_id,
        "recipe_scale": target.recipe_scale,
        "route": target.route,
        "shopping_list_ids": list_ids,
    }


def _response_from_routed(barcode: str, targets: list[BarcodeTarget], routed: dict, paused: bool) -> ScanResponse:
    names = routed.get("names") or [target.target_name or target.target_id for target in targets]
    result = routed.get("result", "error")
    item_text = " + ".join(names[:3]) + (f" +{len(names) - 3}" if len(names) > 3 else "")
    return ScanResponse(
        result=result,
        item=item_text or barcode,
        via="multi" if len(targets) > 1 else (
            routed.get("results", [{}])[0].get("via") if routed.get("results") else None
        ),
        needs_action=result in {"error", "partial", "needs_mapping"},
        action_url=_build_action_url(barcode) if result in {"error", "partial", "needs_mapping"} else None,
        paused=paused,
    )


def _process_targets(barcode: str, targets: list[BarcodeTarget], db: Session, paused: bool) -> ScanResponse:
    routed = route_targets(barcode, targets, db, paused=paused)
    resp = _response_from_routed(barcode, targets, routed, paused)
    first = targets[0] if targets else None
    _save_activity(
        barcode,
        "Scanned (scan & link)" if paused else (
            "Added to destinations" if resp.result == "added"
            else "Partially routed" if resp.result == "partial"
            else "Routing failed"
        ),
        resp.item or barcode,
        resp.result,
        db,
        target_type=first.target_type if first else None,
        target_id=first.target_id if first else None,
        target_name=resp.item or (first.target_name if first else None),
        targets=[_target_snapshot(target) for target in targets],
    )
    if resp.needs_action:
        _save_notification(barcode, "Routing needs attention", resp.item or barcode, resp.result, db)
    _emit_scan_event(barcode, resp, target_count=len(targets))
    return resp


def _ensure_raw_custom_cache(barcode: str, db: Session) -> BarcodeCache:
    cached = db.get(BarcodeCache, barcode)
    if cached:
        return cached
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
    return cached


def _process_scan(barcode: str, db: Session, background_tasks: BackgroundTasks) -> ScanResponse:
    paused = is_paused(db)

    if barcode.upper().startswith("ACTION:"):
        return _process_action_code(barcode, db, background_tasks, paused)

    targets = ensure_targets(barcode, db)
    if targets:
        return _process_targets(barcode, targets, db, paused)

    if barcode.upper().startswith("GENERIC:"):
        term = unquote(barcode[len("GENERIC:"):].strip())
        resp = _handle_generic(term, barcode, db, paused=paused)
        targets = ensure_targets(barcode, db)
        _save_activity(
            barcode,
            "Scanned (scan & link)" if paused else (
                "Added to destination" if resp.result == "added"
                else "Queued" if resp.result == "queued"
                else "Generic scan"
            ),
            resp.item or term or barcode,
            resp.result,
            db,
            targets=[_target_snapshot(target) for target in targets] if targets else None,
        )
        if resp.needs_action:
            _save_notification(barcode, "Generic scan needs attention", resp.item or term or barcode, resp.result, db)
        _emit_scan_event(barcode, resp, target_count=len(targets))
        return resp

    cached = db.get(BarcodeCache, barcode)
    # Product lookup providers are numeric-code oriented. Any raw alphanumeric
    # scanner value is still a valid custom barcode and must reach the mapping UI.
    if not barcode.isdigit() and cached is None:
        cached = _ensure_raw_custom_cache(barcode, db)

    needs_lookup = cached is None
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

    if not cached.found:
        if paused or settings.unknown_barcode_action == "notify_only" or not barcode.isdigit():
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
        _save_activity(
            barcode,
            "Unknown barcode (scan & link)" if paused else "Unknown barcode",
            barcode,
            "unknown",
            db,
        )
        _save_notification(
            barcode,
            "Unknown barcode (scan & link)" if paused else "Unknown barcode",
            "Not found / not linked yet",
            "unknown",
            db,
        )
        _emit_scan_event(barcode, resp)
        return resp

    display_title = cached.display_title or barcode
    display_brand = cached.display_brand
    item_id = try_auto_map(barcode, display_title, display_brand, db)
    if item_id:
        targets = ensure_targets(barcode, db)
        resp = _process_targets(barcode, targets, db, paused)
        resp.brand = display_brand
        resp.quantity = cached.quantity
        resp.needs_action = True
        resp.action_url = _build_action_url(barcode)
        _save_notification(barcode, "Auto-linked — review", f"{display_title} → {resp.item}", "auto_mapped", db)
        return resp

    note = display_title
    if paused or settings.unknown_barcode_action == "notify_only":
        resp = ScanResponse(
            result="needs_mapping",
            item=note,
            paused=paused,
            brand=display_brand,
            quantity=cached.quantity,
            needs_action=True,
            action_url=_build_action_url(barcode),
        )
        _save_activity(
            barcode,
            "Not linked (scan & link)" if paused else "Not linked",
            note,
            "needs_mapping",
            db,
        )
        _save_notification(barcode, "Not linked", f"{note} — tap to link to a Mealie Food or recipe", "needs_mapping", db)
    else:
        success, shopping_item_id = add_shopping_note(note)
        if success:
            if shopping_item_id:
                cached.shopping_item_id = shopping_item_id
                db.commit()
            resp = ScanResponse(
                result="added_as_note",
                item=note,
                via="note",
                brand=display_brand,
                quantity=cached.quantity,
                needs_action=True,
                action_url=_build_action_url(barcode),
            )
            _save_activity(barcode, "Added to list", note + " (via note)", "added_as_note", db)
            _save_notification(barcode, "Not linked", f"{note} — tap to link to a Mealie Food or recipe", "needs_mapping", db)
        else:
            _enqueue_note(barcode, note, db)
            resp = ScanResponse(
                result="queued",
                item=note,
                via="note",
                brand=display_brand,
                quantity=cached.quantity,
                needs_action=True,
                action_url=_build_action_url(barcode),
            )
            _save_activity(barcode, "Queued", note, "queued", db)
    _emit_scan_event(barcode, resp)
    return resp


def _emit_scan_event(barcode: str, resp: ScanResponse, target_count: int = 1):
    scan_events.publish_threadsafe("scan", {
        "barcode": barcode,
        "result": resp.result,
        "item": resp.item,
        "paused": resp.paused,
        "target_count": target_count,
    })


def _save_notification(barcode: str, title: str, message: str, result: str, db: Session):
    existing = db.query(Activity).filter(
        Activity.barcode == barcode,
        Activity.is_read == False,
        Activity.is_dismissed == False,
    ).first()
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
    target_type: str | None = None,
    target_id: str | None = None,
    target_name: str | None = None,
    targets: list[dict] | None = None,
):
    snapshot = targets[0] if targets else {}
    if targets and not target_id:
        target_type = snapshot.get("type")
        target_id = snapshot.get("id")
        target_name = snapshot.get("name")
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
        targets_json=json.dumps(targets) if targets else None,
        quantity_snapshot=(snapshot.get("quantity") if snapshot.get("type") == "food" else None),
        unit_id_snapshot=(snapshot.get("unit_id") if snapshot.get("type") == "food" else None),
        recipe_scale_snapshot=(snapshot.get("recipe_scale") if snapshot.get("type") == "recipe" else None),
    ))
    db.commit()


def _handle_generic(term: str, barcode: str, db: Session, paused: bool = False) -> ScanResponse:
    from rapidfuzz import fuzz

    if not term:
        return ScanResponse(result="unknown", item=None, needs_action=True, action_url=_build_action_url(barcode))

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
                    score = max(score, fuzz.token_sort_ratio(term.lower(), str(alias).lower()))
            except (json.JSONDecodeError, TypeError):
                pass
        if score > best_score:
            best_score = score
            best_item = item

    if best_item and best_score >= settings.fuzzy_match_threshold:
        add_target(
            barcode,
            "food",
            best_item.id,
            best_item.name,
            db,
            quantity=1.0,
            unit_id=best_item.default_unit_id,
            mapped_by="generic",
        )
        targets = ensure_targets(barcode, db)
        routed = route_targets(barcode, targets, db, paused=paused)
        # Do not call _process_targets() here: the outer GENERIC branch owns the
        # single Activity/SSE write for this physical scan.
        return _response_from_routed(barcode, targets, routed, paused)

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


def _enqueue_note(barcode: str, note: str, db: Session) -> None:
    list_id = get_default_shopping_list_id(db)
    payload = {"note": note}
    if list_id:
        payload["shoppingListId"] = list_id
    enqueue_retry(barcode, payload, db)


class AppScanRequest(BaseModel):
    content: str = Field(..., max_length=256)
    deviceId: str = Field(..., max_length=256)
    model_config = {"extra": "ignore"}


@router.post("/scan/app", response_model=ScanResponse)
def scan_barcode_app(
    body: AppScanRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
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
