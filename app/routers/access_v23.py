from __future__ import annotations

import os
import shutil
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.access_v23 import (
    PERMISSION_CATALOG,
    has_permission,
    personal_theme,
    personal_theme_css,
    permissions_for_user,
    save_personal_theme,
    set_permissions,
)
from app.config import settings
from app.database import get_db
from app.models import Activity, ApiToken, BarcodeCache, BarcodeMapping, Item, RetryQueue, User
from app.templating import templates
from app.theme import THEME_CHOICES, THEME_DEFAULTS

router = APIRouter()


def _current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    return db.get(User, int(user_id)) if user_id else None


def _allowed(request: Request, db: Session, permission: str) -> bool:
    if request.session.get("is_admin", False):
        return True
    return has_permission(db, request.session.get("user_id"), permission)


def _dir_size(path: str) -> tuple[int, int]:
    total = 0
    files = 0
    try:
        for root, dirs, names in os.walk(path):
            dirs[:] = [name for name in dirs if not os.path.islink(os.path.join(root, name))]
            for name in names:
                full = os.path.join(root, name)
                if os.path.islink(full) or name.endswith(".backup"):
                    continue
                try:
                    total += os.path.getsize(full)
                    files += 1
                except OSError:
                    pass
    except OSError:
        pass
    return total, files


def _storage_info(db: Session) -> dict:
    db_path = settings.db_path
    root = os.path.dirname(db_path) or "."
    try:
        db_bytes = os.path.getsize(db_path)
        modified = datetime.fromtimestamp(os.path.getmtime(db_path)).isoformat()
    except OSError:
        db_bytes = 0
        modified = None
    total_bytes, files = _dir_size(root)
    return {
        "db_path": db_path,
        "data_root": root,
        "database_bytes": db_bytes,
        "system_data_bytes": total_bytes,
        "other_bytes": max(0, total_bytes - db_bytes),
        "file_count": files,
        "modified_at": modified,
        "tables": {
            "barcode_cache": db.query(BarcodeCache).count(),
            "barcode_mappings": db.query(BarcodeMapping).count(),
            "items": db.query(Item).count(),
            "activities": db.query(Activity).count(),
            "retry_queue": db.query(RetryQueue).count(),
            "api_tokens": db.query(ApiToken).count(),
        },
    }


@router.get("/api/access/me")
def access_me(request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        return JSONResponse({"error": "login required"}, status_code=401)
    return {
        "user_id": user.id,
        "username": user.username,
        "is_admin": user.is_admin,
        "permissions": permissions_for_user(db, user),
    }


@router.get("/api/access/users")
def access_users(request: Request, db: Session = Depends(get_db)):
    if not _allowed(request, db, "users"):
        return JSONResponse({"error": "user-management permission required"}, status_code=403)
    users = db.query(User).order_by(User.created_at).all()
    return {
        "catalog": PERMISSION_CATALOG,
        "users": [
            {
                "id": user.id,
                "username": user.username,
                "is_admin": user.is_admin,
                "permissions": permissions_for_user(db, user),
            }
            for user in users
        ],
    }


@router.post("/api/access/users/{user_id}")
async def access_update_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not _allowed(request, db, "users"):
        return JSONResponse({"error": "user-management permission required"}, status_code=403)
    user = db.get(User, user_id)
    if not user:
        return JSONResponse({"error": "user not found"}, status_code=404)
    body = await request.json()
    values = body.get("permissions") if isinstance(body, dict) else None
    if not isinstance(values, dict):
        return JSONResponse({"error": "permissions object required"}, status_code=400)
    return {"ok": True, "permissions": set_permissions(db, user, values)}


# Personal appearance overrides. These routes intentionally precede the legacy
# global theme routes in main.py; every signed-in user owns their appearance.
@router.get("/api/theme")
def api_personal_theme(request: Request, db: Session = Depends(get_db)):
    return personal_theme(db, request.session.get("user_id"))


@router.post("/api/theme/mode")
async def api_personal_theme_mode(request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        return JSONResponse({"error": "login required"}, status_code=401)
    body = await request.json()
    mode = str(body.get("mode", "light")) if isinstance(body, dict) else "light"
    if mode not in {"light", "dark"}:
        return JSONResponse({"error": "invalid mode"}, status_code=400)
    theme = save_personal_theme(db, user.id, {"mode": mode})
    return {"ok": True, "theme": theme}


@router.get("/user-theme.css")
def user_theme_css(request: Request, db: Session = Depends(get_db)):
    return Response(
        personal_theme_css(db, request.session.get("user_id")),
        media_type="text/css",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/profile/appearance", response_class=HTMLResponse)
def profile_appearance(request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "profile_appearance.html", {
        "theme": personal_theme(db, user.id),
        "theme_choices": THEME_CHOICES,
    })


@router.post("/profile/appearance")
async def profile_appearance_save(request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    values = {
        "mode": form.get("theme_mode", THEME_DEFAULTS["mode"]),
        "color": form.get("theme_color", THEME_DEFAULTS["color"]),
        "font": form.get("theme_font", THEME_DEFAULTS["font"]),
        "base": form.get("theme_base", THEME_DEFAULTS["base"]),
        "radius": form.get("theme_radius", THEME_DEFAULTS["radius"]),
        "date_style": form.get("theme_date_style", THEME_DEFAULTS["date_style"]),
        "epaper": "true" if form.get("theme_epaper") else "false",
        "contrast": form.get("theme_contrast", THEME_DEFAULTS["contrast"]),
    }
    # build_theme_css/save path validates unsupported values by falling back in
    # the UI; store only values represented by the form choices/ranges.
    if values["mode"] not in THEME_CHOICES["mode"]:
        values["mode"] = THEME_DEFAULTS["mode"]
    if values["color"] not in THEME_CHOICES["color"]:
        values["color"] = THEME_DEFAULTS["color"]
    if values["font"] not in THEME_CHOICES["font"]:
        values["font"] = THEME_DEFAULTS["font"]
    if values["base"] not in THEME_CHOICES["base"]:
        values["base"] = THEME_DEFAULTS["base"]
    if values["radius"] not in THEME_CHOICES["radius"]:
        values["radius"] = THEME_DEFAULTS["radius"]
    save_personal_theme(db, user.id, values)
    return RedirectResponse("/profile/appearance?saved=1", status_code=303)


@router.get("/api/system/storage")
def system_storage(request: Request, db: Session = Depends(get_db)):
    if not _allowed(request, db, "database"):
        return JSONResponse({"error": "database permission required"}, status_code=403)
    return _storage_info(db)


@router.get("/database", response_class=HTMLResponse)
def database_page(request: Request, db: Session = Depends(get_db)):
    if not _allowed(request, db, "database"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "database_access.html", {"admin_info": _storage_info(db)})


@router.post("/database/backup")
def database_backup(request: Request, db: Session = Depends(get_db)):
    if not _allowed(request, db, "database"):
        return RedirectResponse("/", status_code=303)
    db_path = settings.db_path
    if not os.path.isfile(db_path):
        return RedirectResponse("/database", status_code=303)
    backup_path = db_path + ".backup"
    shutil.copy2(db_path, backup_path)
    return FileResponse(backup_path, media_type="application/octet-stream", filename="barcode.db")


@router.post("/database/purge/{table}")
def database_purge(table: str, request: Request, db: Session = Depends(get_db)):
    if not _allowed(request, db, "database"):
        return RedirectResponse("/", status_code=303)
    table_map = {
        "barcode_cache": BarcodeCache,
        "barcode_mappings": BarcodeMapping,
        "items": Item,
        "activities": Activity,
        "retry_queue": RetryQueue,
    }
    model = table_map.get(table)
    if not model:
        return RedirectResponse("/database", status_code=303)
    if model is Item:
        db.query(BarcodeMapping).delete()
    db.query(model).delete()
    db.commit()
    return RedirectResponse("/database", status_code=303)
