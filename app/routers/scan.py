import json
import logging
from datetime import timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_token
from app.config import settings
from app.database import get_db
from app.events import scan_events
from app.models import Activity, BarcodeCache, BarcodeMapping, Item
from app.pause import is_paused
from app.services.barcode_lookup import enrich_barcode_background, needs_background_enrich, perform_lookup
from app.services.fuzzy import try_auto_map
from app.services.homeassistant import notify_scan as ha_notify_scan, should_send_scan_webhook
from app.services.mealie import (
    add_recipe_to_shopping_list,
    add_shopping_note,
    add_to_shopping_list_by_item,
    add_to_shopping_list_by_note,
    enqueue_retry,
)
from app.utils import utcnow

logger = logging.getLogger(__name__)
router = APIRouter()


def _build_action_url(barcode: str) -> str:
    encoded = quote(barcode, safe="")
    base = settings.middleware_base_url.rstrip("/")
    return f"{base}/barcodes/{encoded}" if base else f"/barcodes/{encoded}"


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
        and resp.result not in ("unknown", "needs_mapping", "error")
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
        db.rollback()
        return ScanResponse(result="error", item=barcode, via=None)


def _process_scan(barcode: str, db: Session, background_tasks: BackgroundTasks) -> ScanResponse:
    paused = is_paused(db)

    if not barcode.upper().startswith("GENERIC:") and not barcode.isdigit():
        raise HTTPException(
            status_code=422,
            detail="Invalid barcode format — only numeric barcodes and GENERIC: codes are accepted",
        )

    mapping = db.get(BarcodeMapping, barcode)
    if mapping:
        cached = db.get(BarcodeCache, barcode)

        if mapping.target_type == "recipe":
            recipe_name = mapping.target_name or f"Recipe {mapping.target_id}"
            if paused:
                resp = ScanResponse(
                    result="added",
                    item=recipe_name,
                    via=None,
                    paused=True,
                    item_source="recipe",
                )
                _save_activity(barcode, "Scanned (scan & link)", recipe_name, resp.result, db)
            else:
                success = add_recipe_to_shopping_list(
                    mapping.target_id,
                    mapping.recipe_scale or 1.0,
                )
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
                    "Added recipe to list" if success else "Recipe add failed",
                    recipe_name,
                    resp.result,
                    db,
                )
            _emit_scan_event(barcode, resp)
            return resp

        item = db.get(Item, mapping.target_id)
        item_name = item.name if item else (mapping.target_name or barcode)
        if not item:
            resp = ScanResponse(
                result="needs_mapping",
                item=item_name,
                via=None,
                needs_action=True,
                action_url=_build_action_url(barcode),
            )
            _emit_scan_event(barcode, resp)
            _save_activity(barcode, "Broken Food mapping", item_name, resp.result, db)
            _save_notification(
                barcode,
                "Broken Food mapping",
                f"{item_name} no longer exists in the local Mealie Food cache",
                "needs_mapping",
                db,
            )
            return resp

        if paused:
            resp = ScanResponse(
                result="added",
                item=item_name,
                via=None,
                paused=True,
                brand=cached.brand if cached else None,
                quantity=cached.quantity if cached else None,
                item_source=item.source,
            )
            _save_activity(barcode, "Scanned (scan & link)", item_name, resp.result, db)
        else:
            resp = _add_via_item(item, item_name, barcode, db, cached=cached, mapping=mapping)
            _save_activity(
                barcode,
                "Added to list" if resp.result == "added" else "Queued",
                item_name,
                resp.result,
                db,
            )
        _emit_scan_event(barcode, resp)
        return resp

    if barcode.upper().startswith("GENERIC:"):
        term = barcode[len("GENERIC:"):].strip()
        resp = _handle_generic(term, barcode, db, paused=paused)
        _save_activity(
            barcode,
            "Scanned (scan & link)" if paused else ("Added to list" if resp.result.startswith("added") else "Queued"),
            resp.item or term or barcode,
            resp.result,
            db,
        )
        _emit_scan_event(barcode, resp)
        return resp

    cached = db.get(BarcodeCache, barcode)
    needs_lookup = cached is None
    if cached is not None and not cached.found and cached.lookup_attempted_at:
        attempted = cached.lookup_attempted_at
        if attempted.tzinfo is None:
            attempted = attempted.replace(tzinfo=timezone.utc)
        if utcnow() > attempted + timedelta(days=settings.lookup_ttl_days):
            needs_lookup = True

    if needs_lookup:
        cached = perform_lookup(barcode, db)

    if needs_lookup and needs_background_enrich(cached):
        background_tasks.add_task(enrich_barcode_background, barcode)

    if not cached.found:
        if paused or settings.unknown_barcode_action == "notify_only":
            resp = ScanResponse(result="unknown", item=barcode, via=None, paused=paused)
        else:
            success, shopping_item_id = add_shopping_note(barcode)
            if success:
                if shopping_item_id:
                    cached.shopping_item_id = shopping_item_id
                    db.commit()
            else:
                _enqueue_note(barcode, barcode, db)
            resp = ScanResponse(result="unknown", item=barcode, via="note")

        resp.needs_action = True
        resp.action_url = _build_action_url(barcode)
        _emit_scan_event(barcode, resp)
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
            "Not found in any product database",
            "unknown",
            db,
        )
        return resp

    item_id = try_auto_map(barcode, cached.title or barcode, cached.brand, db)
    if item_id:
        item = db.get(Item, item_id)
        item_name = item.name if item else cached.title or barcode
        mapping = db.get(BarcodeMapping, barcode)
        if paused:
            resp = ScanResponse(
                result="added",
                item=item_name,
                via=None,
                paused=True,
                brand=cached.brand,
                quantity=cached.quantity,
                item_source=item.source if item else None,
                needs_action=True,
                action_url=_build_action_url(barcode),
            )
            _save_activity(barcode, "Scanned (scan & link)", item_name, resp.result, db)
        else:
            resp = _add_via_item(item, item_name, barcode, db, cached=cached, mapping=mapping)
            resp.needs_action = True
            resp.action_url = _build_action_url(barcode)
            _save_activity(barcode, "Added to list", item_name, resp.result, db)
        _emit_scan_event(barcode, resp)
        _save_notification(
            barcode,
            "Auto-linked — review",
            f"{cached.title or barcode} → {item_name}",
            "auto_mapped",
            db,
        )
        return resp

    note = cached.title or barcode
    if paused or settings.unknown_barcode_action == "notify_only":
        resp = ScanResponse(
            result="needs_mapping",
            item=note,
            via=None,
            paused=paused,
            brand=cached.brand,
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
        _save_notification(
            barcode,
            "Not linked",
            f"{note} — tap to link to a Mealie Food or recipe",
            "needs_mapping",
            db,
        )
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
                brand=cached.brand,
                quantity=cached.quantity,
                needs_action=True,
                action_url=_build_action_url(barcode),
            )
            _save_activity(barcode, "Added to list", note + " (via note)", "added_as_note", db)
            _save_notification(
                barcode,
                "Not linked",
                f"{note} — tap to link to a Mealie Food or recipe",
                "needs_mapping",
                db,
            )
        else:
            _enqueue_note(barcode, note, db)
            resp = ScanResponse(
                result="queued",
                item=note,
                via="note",
                brand=cached.brand,
                quantity=cached.quantity,
                needs_action=True,
                action_url=_build_action_url(barcode),
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
    })


def _save_notification(barcode: str, title: str, message: str, result: str, db: Session):
    existing = db.query(Activity).filter(
        Activity.barcode == barcode,
        Activity.is_read == False,
    ).first()
    if existing:
        return
    db.add(Activity(barcode=barcode, title=title, message=message, result=result))
    db.commit()


def _save_activity(barcode: str, title: str, message: str, result: str, db: Session):
    db.add(Activity(
        barcode=barcode,
        title=title,
        message=message,
        result=result,
        is_read=True,
        is_dismissed=True,
        is_scan_event=True,
    ))
    db.commit()


def _handle_generic(term: str, barcode: str, db: Session, paused: bool = False) -> ScanResponse:
    """Resolve GENERIC:<name> and persist the successful Food mapping."""
    from rapidfuzz import fuzz

    if not term:
        return ScanResponse(result="unknown", item=None, via=None)

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
            return ScanResponse(
                result="added",
                item=best_item.name,
                via=None,
                paused=True,
                item_source=best_item.source,
            )

        return _add_via_item(best_item, best_item.name, barcode, db, cached=cached, mapping=mapping)

    if paused:
        return ScanResponse(result="added_as_note", item=term, via=None, paused=True)

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
    brand = cached.brand if cached else None
    package_quantity = cached.quantity if cached else None
    item_source = item.source if item else None

    if item and item.source == "mealie":
        list_quantity = mapping.quantity if mapping else 1.0
        unit_id = mapping.unit_id if mapping else None
        success = add_to_shopping_list_by_item(item.id, list_quantity or 1.0, unit_id)
        if success:
            return ScanResponse(
                result="added",
                item=item_name,
                via="item_id",
                brand=brand,
                quantity=package_quantity,
                item_source=item_source,
            )

        payload = {
            "shoppingListId": settings.mealie_shopping_list_id,
            "foodId": item.id,
            "quantity": list_quantity or 1.0,
        }
        if unit_id:
            payload["unitId"] = unit_id
        enqueue_retry(barcode, payload, db)
        return ScanResponse(
            result="queued",
            item=item_name,
            via="item_id",
            brand=brand,
            quantity=package_quantity,
            item_source=item_source,
        )

    note = item.name if item else item_name
    success = add_to_shopping_list_by_note(note)
    if success:
        return ScanResponse(
            result="added",
            item=note,
            via="note",
            brand=brand,
            quantity=package_quantity,
            item_source=item_source,
        )

    _enqueue_note(barcode, note, db)
    return ScanResponse(
        result="queued",
        item=note,
        via="note",
        brand=brand,
        quantity=package_quantity,
        item_source=item_source,
    )


def _enqueue_note(barcode: str, note: str, db: Session) -> None:
    enqueue_retry(barcode, {
        "shoppingListId": settings.mealie_shopping_list_id,
        "note": note,
    }, db)


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
        db.rollback()
        return ScanResponse(result="error", item=barcode, via=None)
