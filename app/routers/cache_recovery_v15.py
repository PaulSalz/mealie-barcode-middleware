from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require_token, require_token_no_telemetry
from app.database import get_db
from app.models import Activity, BarcodeCache, BarcodeMapping, BarcodeTarget
from app.routers import barcodes as barcode_routes
from app.routers import scan as legacy_scan
from app.routers import scan_fast_v11
from app.utils import utcnow

router = APIRouter()


def _has_local_barcode_state(barcode: str, db: Session) -> bool:
    if db.get(BarcodeMapping, barcode):
        return True
    if db.query(BarcodeTarget.id).filter(BarcodeTarget.barcode == barcode).first():
        return True
    return db.query(Activity.id).filter(Activity.barcode == barcode).first() is not None


def _ensure_cache_shell(barcode: str, db: Session, *, only_if_known: bool = False) -> BarcodeCache | None:
    """Restore the local cache identity without doing any external product lookup.

    Barcode targets/mappings deliberately live independently from BarcodeCache, so
    clearing lookup cache must not make an otherwise valid mapped barcode disappear
    from the UI. A physical scan is enough to recreate a minimal cache shell.
    """
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
        # /scanner/received and /scan can arrive almost simultaneously. If both
        # try to rebuild the same row after a cache reset, keep the winner.
        db.rollback()
        return db.get(BarcodeCache, barcode)


@router.post("/scanner/received")
def scanner_received_with_cache_recovery(
    body: legacy_scan.ScanRequest,
    token=Depends(require_token_no_telemetry),
    db: Session = Depends(get_db),
):
    barcode = body.barcode.strip()
    if not barcode:
        raise HTTPException(status_code=422, detail="Barcode cannot be empty")
    _ensure_cache_shell(barcode, db)
    return scan_fast_v11.fast_scanner_received(body=body, _token=token, db=db)


@router.post("/scan", response_model=legacy_scan.ScanResponse)
def scan_with_cache_recovery(
    body: legacy_scan.ScanRequest,
    background_tasks: BackgroundTasks,
    token=Depends(require_token),
    db: Session = Depends(get_db),
):
    barcode = body.barcode.strip()
    if not barcode:
        raise HTTPException(status_code=422, detail="Barcode cannot be empty")
    _ensure_cache_shell(barcode, db)
    return scan_fast_v11.fast_scan_barcode(
        body=body,
        background_tasks=background_tasks,
        _token=token,
        db=db,
    )


@router.get("/barcodes/{barcode:path}", response_class=HTMLResponse)
def barcode_detail_with_cache_recovery(
    request: Request,
    barcode: str,
    db: Session = Depends(get_db),
):
    # Self-heal barcodes that already have targets/mappings/history from before a
    # lookup-cache reset. Do not create rows for arbitrary manually typed URLs.
    _ensure_cache_shell(barcode, db, only_if_known=True)
    return barcode_routes.barcode_detail(request=request, barcode=barcode, db=db)
