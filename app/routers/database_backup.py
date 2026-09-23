from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.access_v23 import has_permission
from app.config import settings
from app.database import get_db
from app.services.database_backup import create_verified_backup, remove_backup

logger = logging.getLogger(__name__)
router = APIRouter()


def _backup_response() -> FileResponse | JSONResponse:
    try:
        backup_path = create_verified_backup(settings.db_path)
    except Exception as exc:
        logger.exception("Verified SQLite backup failed")
        return JSONResponse({"error": f"Backup failed: {exc}"}, status_code=500)
    return FileResponse(
        backup_path,
        media_type="application/octet-stream",
        filename="barcode.db",
        background=BackgroundTask(remove_backup, backup_path),
    )


@router.post("/settings/admin/backup")
def admin_backup(request: Request):
    """Create a WAL-safe verified backup for the legacy admin settings page."""
    if not request.session.get("is_admin", False):
        return RedirectResponse("/settings?tab=mealie", status_code=303)
    return _backup_response()


@router.post("/database/backup")
def database_backup(request: Request, db: Session = Depends(get_db)):
    """Create a WAL-safe verified backup for users with database permission."""
    user_id = request.session.get("user_id")
    if not request.session.get("is_admin", False) and not has_permission(db, user_id, "database"):
        return RedirectResponse("/", status_code=303)
    return _backup_response()
