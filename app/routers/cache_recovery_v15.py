from __future__ import annotations

import json
from datetime import timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require_token, require_token_no_telemetry
from app.database import get_db
from app.models import Activity, BarcodeCache, BarcodeTarget
from app.models_scan_delivery import ScanDelivery
from app.routers import barcodes as barcode_routes
from app.routers import scan as legacy_scan
from app.routers import scan_fast_v11
from app.utils import utcnow

router = APIRouter()
_DELIVERY_LEASE = timedelta(minutes=2)
_DELIVERY_RETENTION = timedelta(days=7)


def _has_local_barcode_state(barcode: str, db: Session) -> bool:
    if db.query(BarcodeTarget.id).filter(BarcodeTarget.barcode == barcode).first():
        return True
    return db.query(Activity.id).filter(Activity.barcode == barcode).first() is not None


def _has_routable_barcode_state(barcode: str, db: Session) -> bool:
    """Return True only for canonical target state that can route locally."""
    return db.query(BarcodeTarget.id).filter(
        BarcodeTarget.barcode == barcode,
        BarcodeTarget.enabled == True,
    ).first() is not None


def _drop_stale_lookup_shell(barcode: str, db: Session) -> None:
    """Remove old recovery shells that never represented a provider lookup."""
    if not barcode.isdigit() or _has_routable_barcode_state(barcode, db):
        return
    cached = db.get(BarcodeCache, barcode)
    if not cached:
        return
    if cached.source == "scan" and not cached.found and cached.lookup_attempted_at is None:
        db.delete(cached)
        db.commit()


def _ensure_cache_shell(barcode: str, db: Session, *, only_if_known: bool = False) -> BarcodeCache | None:
    """Restore local cache identity without doing an external product lookup."""
    cached = db.get(BarcodeCache, barcode)
    if cached:
        return cached
    if only_if_known and not _has_local_barcode_state(barcode, db):
        return None

    cached = BarcodeCache(
        barcode=barcode,
        source="action" if barcode.upper().startswith("ACTION:") else "scan",
        found=False,
        lookup_attempted_at=None,
        created_at=utcnow(),
    )
    db.add(cached)
    try:
        db.commit()
        db.refresh(cached)
        return cached
    except IntegrityError:
        db.rollback()
        return db.get(BarcodeCache, barcode)


def _naive_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _delivery_id(request: Request) -> str:
    value = (request.headers.get("X-B2M-Delivery-ID") or "").strip()
    if len(value) > 128:
        raise HTTPException(status_code=400, detail="X-B2M-Delivery-ID is too long")
    return value


def _reserve_delivery(db: Session, delivery_id: str, barcode: str):
    """Reserve one physical scan delivery or replay an already completed result."""
    if not delivery_id:
        return None

    now = utcnow()
    existing = db.get(ScanDelivery, delivery_id)
    if existing:
        if existing.barcode != barcode:
            raise HTTPException(status_code=409, detail="Delivery ID belongs to a different barcode")
        if existing.status_code is not None and existing.response_body:
            try:
                payload = json.loads(existing.response_body)
            except (TypeError, ValueError):
                payload = {"result": "processing", "item": barcode}
            return JSONResponse(
                payload,
                status_code=existing.status_code,
                headers={"X-B2M-Delivery-Replay": "1"},
            )

        created = _naive_utc(existing.created_at)
        now_naive = _naive_utc(now)
        if created and now_naive - created < _DELIVERY_LEASE:
            return JSONResponse(
                {"detail": "Scan delivery is still processing"},
                status_code=409,
                headers={"Retry-After": "1"},
            )

        db.delete(existing)
        db.commit()

    cutoff = _naive_utc(now - _DELIVERY_RETENTION)
    db.query(ScanDelivery).filter(
        ScanDelivery.completed_at.isnot(None),
        ScanDelivery.completed_at < cutoff,
    ).delete(synchronize_session=False)
    db.add(ScanDelivery(delivery_id=delivery_id, barcode=barcode, created_at=now))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return JSONResponse(
            {"detail": "Scan delivery is already processing"},
            status_code=409,
            headers={"Retry-After": "1"},
        )
    return None


def _complete_delivery(db: Session, delivery_id: str, barcode: str, response) -> None:
    if not delivery_id:
        return
    row = db.get(ScanDelivery, delivery_id)
    if not row:
        return
    if hasattr(response, "model_dump"):
        payload = response.model_dump(mode="json")
    elif isinstance(response, dict):
        payload = response
    else:
        payload = {"result": "processing", "item": barcode}
    row.status_code = 200
    row.response_body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    row.completed_at = utcnow()
    db.commit()


def _release_delivery(db: Session, delivery_id: str) -> None:
    if not delivery_id:
        return
    row = db.get(ScanDelivery, delivery_id)
    if row and row.completed_at is None:
        db.delete(row)
        db.commit()


@router.post("/scanner/received")
def scanner_received_with_cache_recovery(
    body: legacy_scan.ScanRequest,
    token=Depends(require_token_no_telemetry),
    db: Session = Depends(get_db),
):
    barcode = body.barcode.strip()
    if not barcode:
        raise HTTPException(status_code=422, detail="Barcode cannot be empty")
    if _has_routable_barcode_state(barcode, db):
        _ensure_cache_shell(barcode, db)
    return scan_fast_v11.fast_scanner_received(body=body, _token=token, db=db)


@router.post("/scan", response_model=legacy_scan.ScanResponse)
def scan_with_cache_recovery(
    body: legacy_scan.ScanRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    token=Depends(require_token),
    db: Session = Depends(get_db),
):
    barcode = body.barcode.strip()
    if not barcode:
        raise HTTPException(status_code=422, detail="Barcode cannot be empty")

    delivery_id = _delivery_id(request)
    replay = _reserve_delivery(db, delivery_id, barcode)
    if replay is not None:
        return replay

    try:
        _drop_stale_lookup_shell(barcode, db)
        if _has_routable_barcode_state(barcode, db):
            _ensure_cache_shell(barcode, db)
        response = scan_fast_v11.fast_scan_barcode(
            body=body,
            background_tasks=background_tasks,
            _token=token,
            db=db,
        )
        _complete_delivery(db, delivery_id, barcode, response)
        return response
    except Exception:
        db.rollback()
        _release_delivery(db, delivery_id)
        raise


@router.get("/barcodes/{barcode:path}", response_class=HTMLResponse)
def barcode_detail_with_cache_recovery(
    request: Request,
    barcode: str,
    db: Session = Depends(get_db),
):
    _ensure_cache_shell(barcode, db, only_if_known=True)
    return barcode_routes.barcode_detail(request=request, barcode=barcode, db=db)
