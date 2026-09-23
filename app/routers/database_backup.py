from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.access_v23 import has_permission
from app.config import settings
from app.database import SessionLocal, get_db
from app.models import SystemState
from app.services.database_backup import create_verified_backup, remove_backup
from app.utils import utcnow

logger = logging.getLogger(__name__)
router = APIRouter()
_LAST_VERIFIED_BACKUP_KEY = "maintenance.last_verified_backup"


def _record_verified_backup() -> None:
    db = SessionLocal()
    try:
        value = utcnow().isoformat()
        row = db.get(SystemState, _LAST_VERIFIED_BACKUP_KEY)
        if row:
            row.value = value
        else:
            db.add(SystemState(key=_LAST_VERIFIED_BACKUP_KEY, value=value))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not record verified backup timestamp")
    finally:
        db.close()


def _backup_response() -> FileResponse | JSONResponse:
    try:
        backup_path = create_verified_backup(settings.db_path)
    except Exception as exc:
        logger.exception("Verified SQLite backup failed")
        return JSONResponse({"error": f"Backup failed: {exc}"}, status_code=500)
    _record_verified_backup()
    return FileResponse(
        backup_path,
        media_type="application/octet-stream",
        filename="barcode.db",
        background=BackgroundTask(remove_backup, backup_path),
    )


def _allowed(request: Request, db: Session) -> bool:
    user_id = request.session.get("user_id")
    return bool(request.session.get("is_admin", False) or has_permission(db, user_id, "database"))


@router.get("/api/database/backup-status")
def backup_status(request: Request, db: Session = Depends(get_db)):
    if not _allowed(request, db):
        return JSONResponse({"error": "permission denied"}, status_code=403)
    row = db.get(SystemState, _LAST_VERIFIED_BACKUP_KEY)
    try:
        size = os.path.getsize(settings.db_path)
    except OSError:
        size = 0
    return {
        "last_verified_backup": row.value if row and row.value else None,
        "database_size_bytes": size,
        "verified": bool(row and row.value),
    }


@router.post("/settings/admin/backup")
def admin_backup(request: Request):
    """Create a WAL-safe verified backup for the admin settings page."""
    if not request.session.get("is_admin", False):
        return RedirectResponse("/settings?tab=mealie", status_code=303)
    return _backup_response()


@router.post("/database/backup")
def database_backup(request: Request, db: Session = Depends(get_db)):
    """Create a WAL-safe verified backup for users with database permission."""
    if not _allowed(request, db):
        return RedirectResponse("/", status_code=303)
    return _backup_response()
