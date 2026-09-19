import json
import logging
from urllib.parse import quote
from datetime import timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_token
from app.config import settings
from app.database import get_db
from app.events import scan_events
from app.models import BarcodeCache, BarcodeMapping, RecipeBarcodeMapping, Item, Activity
from app.services.barcode_lookup import perform_lookup, needs_background_enrich, enrich_barcode_background
from app.services.fuzzy import try_auto_map
from app.services.mealie import (
    add_to_shopping_list_by_item,
    add_to_shopping_list_by_note,
    add_shopping_note,
    add_recipe_to_shopping_list,
    enqueue_retry,
)
from app.services.homeassistant import notify_scan as ha_notify_scan
from app.pause import is_paused
from app.utils import utcnow

logger = logging.getLogger(__name__)
router = APIRouter()


def _build_action_url(barcode: str) -> str:
    encoded = quote(barcode, safe="")
    base = settings.middleware_base_url.rstrip("/")
    if base:
        return f"{base}/barcodes/{encoded}"
    return f"/barcodes/{encoded}"


class ScanRequest(BaseModel):
    barcode: str = Field(..., max_length=256)


class ScanResponse(BaseModel):
    result: str  # added | added_as_note | queued | unknown | needs_mapping | error
    item: str | None = None
    via: str | None = None  # item_id | note | recipe
    needs_action: bool = False
    action_url: str | None = None
    brand: str | None = None
    quantity: str | None = None
    item_source: str | None = None  # mealie | manual | recipe | None
    paused: bool = False


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
        if resp.needs_action:
            added_to_list = resp.via is not None and resp.result not in ("unknown", "needs_mapping") and not resp.paused
            background_tasks.add_task(
                ha_notify_scan,
                barcode,
                resp.item,
                resp.result,
                resp.action_url or "",
                added_to_list,
                resp.paused,
            )
        return resp
    except Exception:
        logger.exception("Unhandled error processing scan for barcode %s", barcode)
        db.rollback()
        return ScanResponse(result="error", item=barcode, via=None)


def _process_scan(barcode: str, db: Session, background_tasks: BackgroundTasks) -> ScanResponse:
    paused = is_paused(db)
    barcode_upper = barcode.upper()

    # Accept numeric product codes and explicit middleware QR/code prefixes.
    if not (
        barcode.isdigit()
        or barcode_upper.startswith("GENERIC:")
        or barcode_upper.startswith("RECIPE:")
    ):
        logger.info("Rejected non-barcode input: %.40s…", barcode)
        raise HTTPException(
            status_code=422,
            detail="Invalid barcode format — numeric, GENERIC: and RECIPE: codes are accepted",
        )

    # Recipe mappings take precedence over food mappings if data ever overlaps.
    recipe_mapping = db.get(RecipeBarcodeMapping, barcode)
    if recipe_mapping:
        return _add_via_recipe_mapping(recipe_mapping, barcode, db, paused)

    # Direct recipe sticker: RECIPE:<Mealie recipe UUID>.
    if barcode_upper.startswith("RECIPE:"):
        recipe_id = barcode[len("RECIPE:"):].strip()
        if not recipe_id:
            raise HTTPException(status_code=422, detail="RECIPE: code has no recipe id")
        temp_mapping = RecipeBarcodeMapping(
            barcode=barcode,
            recipe_id=recipe_id,
            recipe_name=recipe_id,
            recipe_scale=1.0,
            mapped_by="direct",
        )
        return _add_via_recipe_mapping(temp_mapping, barcode, db, paused, persist=False)

    # Existing structured food mapping.
    mapping = db.get(BarcodeMapping, barcode)
    if mapping:
        item = db.get(Item, mapping.item_id)
        item_name = item.name if item else barcode
        cached = db.get(BarcodeCache, barcode)
        if paused:
            brand = cached.brand if cached else None
            product_quantity = cached.quantity if cached else None
            item_source = item.source if item else None
            resp = ScanResponse(
                result="added",
                item=item_name,
                via=None,
                paused=True,
                brand=brand,
                quantity=product_quantity,
                item_source=item_source,
            )
            _emit_scan_event(barcode, resp)
            _save_activity(barcode, "Scanned (scan & link)", item_name, resp.result, db)
        else:
            resp = _add_via_item(item, item_name, barcode, db, cached=cached, mapping=mapping)
            _emit_scan_event(barcode, resp)
            _save_activity(barcode, "Added to list", item_name, resp.result, db)
        return resp

    # Generic kitchen label, e.g. GENERIC:Brot.
    if barcode_upper.startswith("GENERIC:"):
        term = barcode[len("GENERIC:"):].strip()
        resp = _handle_generic(term, barcode, db, paused=paused)
        _emit_scan_event(barcode, resp)
        return resp

    # Standard product barcode lookup.
    cached = db.get(BarcodeCache, barcode)
    needs_lookup = False

    if cached is None:
        needs_lookup = True
    elif not cached.found and cached.lookup_attempted_at:
        attempted = cached.lookup_attempted_at
        if attempted.tzinfo is None:
            attempted = attempted.replace(tzinfo=timezone.utc)
        ttl_expiry = attempted + timedelta(days=settings.lookup_ttl_days)
        if utcnow() > ttl_expiry:
            needs_lookup = True

    if needs_lookup:
        cached = perform_lookup(barcode, db)

    if needs_lookup and needs_background_enrich(cached):
        background_tasks.add_task(enrich_barcode_background, barcode)

    if not cached.found:
        note = barcode
        if paused or settings.unknown_barcode_action == "notify_only":
            resp = ScanResponse(result="unknown", item=barcode, via=None, paused=paused)
        else:
            success, item_id = add_shopping_note(note)
            if success:
                if item_id and cached:
                    cached.shopping_item_id = item_id
                    db.commit()
                resp = ScanResponse(result="unknown", item=barcode, via="note")
            else:
                _enqueue_note(barcode, note, db)
                resp = ScanResponse(result="unknown", item=barcode, via="note")
        resp.needs_action = True
        resp.action_url = _build_action_url(barcode)
        _emit_scan_event(barcode, resp)
        title = "Unknown barcode (scan & link)" if paused else "Unknown barcode"
        _save_notification(barcode, title, "Not found in any product database", "unknown", db)
        return resp

    # Fuzzy food auto-mapping.
    item_id = try_auto_map(barcode, cached.title or barcode, cached.brand, db)
    if item_id:
        item = db.get(Item, item_id)
        mapping = db.get(BarcodeMapping, barcode)
        item_name = item.name if item else cached.title or barcode
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

    # Product known externally, but not linked to a Mealie food yet.
    note = cached.title or barcode
    if paused or settings.unknown_barcode_action == "notify_only":
        result_type = "needs_mapping" if cached.found else "unknown"
        resp = ScanResponse(
            result=result_type,
            item=note,
            via=None,
            paused=paused,
            brand=cached.brand,
            quantity=cached.quantity,
            needs_action=True,
            action_url=_build_action_url(barcode),
        )
        activity_title = "Not linked (scan & link)" if paused else "Not linked"
        _save_activity(barcode, activity_title, note, result_type, db)
        _save_notification(barcode, "Not linked", f"{note} — tap to link to a Mealie item", "needs_mapping", db)
    else:
        success, item_id = add_shopping_note(note)
        if success:
            if item_id and cached:
                cached.shopping_item_id = item_id
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
            _save_notification(barcode, "Not linked", f"{note} — tap to link to a Mealie item", "needs_mapping", db)
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
    existing = (
        db.query(Activity)
        .filter(Activity.barcode == barcode, Activity.is_read == False)
        .first()
    )
    if existing:
        return
    db.add(Activity(
        barcode=barcode,
        title=title,
        message=message,
        result=result,
    ))
    db.commit()


def _save_activity(barcode: str, title: str, message: str, result: str, db: Session):
    db.add(Activity(
        barcode=barcode,
        title=title,
        message=message,
        result=result,
        is_read=True,
        is_dismissed=True,
    ))
    db.commit()


def _handle_generic(term: str, barcode: str, db: Session, paused: bool = False) -> ScanResponse:
    """Handle GENERIC: prefixed scans and persist a successful food mapping."""
    from rapidfuzz import fuzz

    if not term:
        return ScanResponse(result="unknown", item=None, via=None)

    existing_cache = db.get(BarcodeCache, barcode)
    if not existing_cache:
        existing_cache = BarcodeCache(
            barcode=barcode,
            source="generic",
            title=term,
            found=True,
            lookup_attempted_at=utcnow(),
            created_at=utcnow(),
        )
        db.add(existing_cache)
        db.commit()

    all_items = db.query(Item).all()
    best_score = 0
    best_item = None
    for item in all_items:
        score = fuzz.token_sort_ratio(term.lower(), item.name.lower())
        if item.aliases:
            try:
                aliases = json.loads(item.aliases)
                for alias in aliases:
                    score = max(score, fuzz.token_sort_ratio(term.lower(), alias.lower()))
            except (json.JSONDecodeError, TypeError):
                pass
        if score > best_score:
            best_score = score
            best_item = item

    if best_item and best_score >= settings.fuzzy_match_threshold:
        mapping = db.get(BarcodeMapping, barcode)
        if not mapping:
            mapping = BarcodeMapping(
                barcode=barcode,
                item_id=best_item.id,
                quantity=1.0,
                unit_id=None,
                mapped_by="auto_confirmed",
            )
            db.add(mapping)
            db.commit()
        if paused:
            resp = ScanResponse(result="added", item=best_item.name, via=None, paused=True)
            _save_activity(barcode, "Scanned (scan & link)", best_item.name, resp.result, db)
            return resp
        return _add_via_item(best_item, best_item.name, barcode, db, mapping=mapping)

    if paused:
        resp = ScanResponse(result="added_as_note", item=term, via=None, paused=True)
        _save_activity(barcode, "Scanned (scan & link)", term, resp.result, db)
        return resp

    success, item_id = add_shopping_note(term)
    if success:
        if item_id and existing_cache:
            existing_cache.shopping_item_id = item_id
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
    """Add to shopping list using the mapped food's barcode-specific defaults."""
    brand = cached.brand if cached else None
    product_quantity = cached.quantity if cached else None
    item_source = item.source if item else None
    mapping = mapping or db.get(BarcodeMapping, barcode)
    shopping_quantity = (mapping.quantity if mapping else 1.0) or 1.0
    unit_id = mapping.unit_id if mapping else None

    if item and item.source == "mealie":
        success = add_to_shopping_list_by_item(
            item.id,
            quantity=shopping_quantity,
            unit_id=unit_id,
        )
        if success:
            return ScanResponse(
                result="added",
                item=item_name,
                via="item_id",
                brand=brand,
                quantity=product_quantity,
                item_source=item_source,
            )

        payload = {
            "shoppingListId": settings.mealie_shopping_list_id,
            "foodId": item.id,
            "quantity": shopping_quantity,
        }
        if unit_id:
            payload["unitId"] = unit_id
        enqueue_retry(barcode, payload, db)
        return ScanResponse(
            result="queued",
            item=item_name,
            via="item_id",
            brand=brand,
            quantity=product_quantity,
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
            quantity=product_quantity,
            item_source=item_source,
        )
    _enqueue_note(barcode, note, db)
    return ScanResponse(
        result="queued",
        item=note,
        via="note",
        brand=brand,
        quantity=product_quantity,
        item_source=item_source,
    )


def _add_via_recipe_mapping(
    mapping: RecipeBarcodeMapping,
    barcode: str,
    db: Session,
    paused: bool,
    persist: bool = True,
) -> ScanResponse:
    """Add a whole recipe through Mealie's native shopping-list recipe reference."""
    display_name = mapping.recipe_name or mapping.recipe_id
    if paused:
        resp = ScanResponse(
            result="added",
            item=display_name,
            via=None,
            paused=True,
            item_source="recipe",
        )
        _emit_scan_event(barcode, resp)
        _save_activity(barcode, "Scanned recipe (scan & link)", display_name, resp.result, db)
        return resp

    success = add_recipe_to_shopping_list(mapping.recipe_id, mapping.recipe_scale or 1.0)
    if success:
        resp = ScanResponse(
            result="added",
            item=display_name,
            via="recipe",
            item_source="recipe",
        )
        _emit_scan_event(barcode, resp)
        _save_activity(barcode, "Recipe added to list", display_name, resp.result, db)
        return resp

    resp = ScanResponse(
        result="error",
        item=display_name,
        via="recipe",
        item_source="recipe",
        needs_action=persist,
        action_url=_build_action_url(barcode) if persist else None,
    )
    _emit_scan_event(barcode, resp)
    _save_activity(barcode, "Recipe add failed", display_name, resp.result, db)
    return resp


def _enqueue_note(barcode: str, note: str, db: Session) -> None:
    payload = {
        "shoppingListId": settings.mealie_shopping_list_id,
        "note": note,
    }
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
        if resp.needs_action:
            added_to_list = resp.via is not None and resp.result not in ("unknown", "needs_mapping") and not resp.paused
            background_tasks.add_task(
                ha_notify_scan,
                barcode,
                resp.item,
                resp.result,
                resp.action_url or "",
                added_to_list,
                resp.paused,
            )
        return resp
    except Exception:
        logger.exception("Unhandled error processing app scan for barcode %s", barcode)
        db.rollback()
        return ScanResponse(result="error", item=barcode, via=None)
