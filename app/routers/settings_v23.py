from __future__ import annotations

import copy
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.access_control import PERMISSION_DEFS, has_permission, permission_map, save_permissions
from app.config import settings
from app.database import get_db
from app.models import Activity, ApiToken, BarcodeCache, BarcodeMapping, Item, RetryQueue, SystemState, User
from app.routers import settings as legacy_settings
from app.services import niimblue
from app.templating import templates
from app.theme import THEME_CHOICES, THEME_DEFAULTS
from app.user_theme import build_user_theme_css, get_user_appearance, save_user_appearance

router = APIRouter()

_PRINTING_TAB = ("printing", "Printer", "ti-printer")


def _allowed_tab_ids(request: Request) -> set[str]:
    if request.session.get("is_admin", False):
        return {tab_id for tab_id, _, _ in legacy_settings._TABS} | {"printing"}
    allowed = {"appearance"}
    if has_permission(request, "printer_settings"):
        allowed.add("printing")
    if has_permission(request, "database_admin"):
        allowed.add("admin")
    return allowed


def _tabs_for_request(request: Request) -> list[tuple[str, str, str]]:
    allowed = _allowed_tab_ids(request)
    tabs = list(legacy_settings._TABS)
    if not any(row[0] == "printing" for row in tabs):
        insert_at = 2 if len(tabs) >= 2 else len(tabs)
        tabs.insert(insert_at, _PRINTING_TAB)
    return [row for row in tabs if row[0] in allowed]


def _sidebar_for_tabs(tabs: list[tuple[str, str, str]]) -> dict[str, list[str]]:
    visible = {row[0] for row in tabs}
    source = copy.deepcopy(legacy_settings._SIDEBAR_GROUPS)
    source.setdefault("Integrations", [])
    if "printing" not in source["Integrations"]:
        source["Integrations"].append("printing")
    result = {}
    for label, ids in source.items():
        keep = [tab_id for tab_id in ids if tab_id in visible]
        if keep:
            result[label] = keep
    return result


def _theme_choices() -> dict:
    values = copy.deepcopy(THEME_CHOICES)
    colors = list(values.get("color", []))
    if "rainbow" not in colors:
        colors.append("rainbow")
    values["color"] = colors
    return values


def _directory_stats(db_path: str) -> dict:
    path = Path(db_path)
    root = path.parent
    total = 0
    file_count = 0
    try:
        for current, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [name for name in dirs if not Path(current, name).is_symlink()]
            for name in files:
                candidate = Path(current, name)
                try:
                    if candidate.is_symlink():
                        continue
                    total += candidate.stat().st_size
                    file_count += 1
                except OSError:
                    pass
    except OSError:
        pass

    def size(candidate: Path) -> int:
        try:
            return candidate.stat().st_size
        except OSError:
            return 0

    db_size = size(path)
    wal_size = size(Path(str(path) + "-wal"))
    shm_size = size(Path(str(path) + "-shm"))
    aux_size = wal_size + shm_size
    return {
        "data_path": str(root),
        "system_size": total,
        "file_count": file_count,
        "db_size": db_size,
        "wal_size": wal_size,
        "shm_size": shm_size,
        "db_aux_size": aux_size,
        "other_size": max(0, total - db_size - aux_size),
    }


def _admin_info(db: Session) -> dict:
    info = legacy_settings._get_admin_info(db)
    info.update(_directory_stats(settings.db_path))
    return info


def _deny(request: Request, permission: str):
    if has_permission(request, permission):
        return None
    return JSONResponse({"error": f"permission required: {permission}"}, status_code=403)


@router.get("/settings", response_class=HTMLResponse)
def settings_page_v23(
    request: Request,
    tab: str | None = Query(None),
    db: Session = Depends(get_db),
):
    tabs = _tabs_for_request(request)
    allowed = {row[0] for row in tabs}
    default_tab = "mealie" if request.session.get("is_admin", False) and "mealie" in allowed else "appearance"
    requested = tab or default_tab
    if requested not in allowed:
        fallback = "appearance" if "appearance" in allowed else (tabs[0][0] if tabs else "appearance")
        return RedirectResponse(f"/settings?tab={fallback}&forbidden=1", status_code=303)

    all_groups = legacy_settings._build_config_groups() if request.session.get("is_admin", False) else []
    active_groups = legacy_settings._TAB_GROUPS.get(requested, [])
    tab_groups = [(name, sections) for name, sections in all_groups if name in active_groups]
    has_editable = any(
        item["editable"]
        for _, sections in tab_groups
        for _, items in sections
        for item in items
    )

    tokens = db.query(ApiToken).order_by(ApiToken.created_at.desc()).all() if requested == "tokens" else []
    users = db.query(User).order_by(User.created_at).all() if requested == "users" else []
    theme = get_user_appearance(db, request.session.get("user_id")) if requested == "appearance" else {}
    admin_info = _admin_info(db) if requested == "admin" else {}
    tab_label = next((label for tid, label, _ in tabs if tid == requested), requested.title())
    descriptions = dict(legacy_settings._TAB_DESCRIPTIONS)
    descriptions["printing"] = "Connection, runtime configuration and roll settings for the label printer."
    descriptions["appearance"] = "Personal interface preferences. These settings apply only to your user account."

    return templates.TemplateResponse(request, "settings.html", {
        "tabs": tabs,
        "sidebar_groups": _sidebar_for_tabs(tabs),
        "current_tab": requested,
        "current_tab_label": tab_label,
        "tab_description": descriptions.get(requested, ""),
        "section_descriptions": legacy_settings._SECTION_DESCRIPTIONS,
        "config_groups": tab_groups,
        "has_editable": has_editable,
        "tokens": tokens,
        "new_token": None,
        "users": users,
        "theme": theme,
        "theme_choices": _theme_choices(),
        "admin_info": admin_info,
    })


@router.get("/theme.css")
def user_theme_css(request: Request, db: Session = Depends(get_db)):
    theme = get_user_appearance(db, request.session.get("user_id"))
    return Response(build_user_theme_css(theme), media_type="text/css", headers={"Cache-Control": "no-cache"})


@router.get("/api/theme")
def api_get_user_theme(request: Request, db: Session = Depends(get_db)):
    return JSONResponse(get_user_appearance(db, request.session.get("user_id")))


@router.post("/api/theme/mode")
async def api_set_user_theme_mode(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "login required"}, status_code=401)
    body = await request.json()
    mode = str(body.get("mode", "light"))
    if mode not in {"light", "dark"}:
        return JSONResponse({"error": "mode must be light or dark"}, status_code=400)
    theme = save_user_appearance(db, user_id, {"mode": mode})
    return {"ok": True, "theme": theme}


@router.post("/settings/theme")
async def save_user_theme_settings(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    values = {
        "mode": form.get("theme_mode", THEME_DEFAULTS["mode"]),
        "color": form.get("theme_color", THEME_DEFAULTS["color"]),
        "font": form.get("theme_font", THEME_DEFAULTS["font"]),
        "base": form.get("theme_base", THEME_DEFAULTS["base"]),
        "radius": form.get("theme_radius", THEME_DEFAULTS["radius"]),
    }
    fresh = save_user_appearance(db, user_id, values)
    request.session["theme_date_style"] = fresh.get("date_style", "medium")
    return RedirectResponse("/settings?tab=appearance&saved=1", status_code=303)


@router.post("/api/theme/accessibility")
async def save_user_accessibility(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "login required"}, status_code=401)
    body = await request.json()
    values = {
        "epaper": "true" if bool(body.get("epaper")) else "false",
        "contrast": body.get("contrast", THEME_DEFAULTS["contrast"]),
    }
    fresh = save_user_appearance(db, user_id, values)
    return {"ok": True, "theme": fresh}


@router.post("/api/theme/preferences")
async def save_user_theme_preferences(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "login required"}, status_code=401)
    body = await request.json()
    values = {}
    if "date_style" in body:
        values["date_style"] = str(body["date_style"])
    if "font_size" in body:
        values["font_size"] = body["font_size"]
    fresh = save_user_appearance(db, user_id, values)
    request.session["theme_date_style"] = fresh.get("date_style", "medium")
    return {"ok": True, "theme": fresh}


@router.get("/api/ui-preferences-v3")
def user_ui_preferences_v3(request: Request, db: Session = Depends(get_db)):
    appearance = get_user_appearance(db, request.session.get("user_id"))
    return {
        "version": "2026.09.22.2",
        "font_size": int(appearance.get("font_size", 100)),
        "date_style": appearance.get("date_style", "medium"),
    }


@router.post("/api/ui-preferences-v3")
async def save_user_ui_preferences_v3(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "login required"}, status_code=401)
    body = await request.json()
    values = {}
    if "font_size" in body:
        try:
            value = int(float(body["font_size"]))
        except (TypeError, ValueError):
            return JSONResponse({"error": "font_size must be numeric"}, status_code=400)
        if not 80 <= value <= 120:
            return JSONResponse({"error": "font_size must be between 80 and 120"}, status_code=400)
        values["font_size"] = value
    if "date_style" in body:
        value = str(body["date_style"])
        if value not in {"short", "medium", "long"}:
            return JSONResponse({"error": "invalid date_style"}, status_code=400)
        values["date_style"] = value
    fresh = save_user_appearance(db, user_id, values)
    request.session["theme_date_style"] = fresh.get("date_style", "medium")
    return {"ok": True, "version": "2026.09.22.2", "font_size": int(fresh.get("font_size", 100)), "date_style": fresh.get("date_style", "medium")}


@router.get("/api/theme/live.css")
def user_live_theme_css(
    mode: str = Query(THEME_DEFAULTS["mode"]),
    color: str = Query(THEME_DEFAULTS["color"]),
    font: str = Query(THEME_DEFAULTS["font"]),
    base: str = Query(THEME_DEFAULTS["base"]),
    radius: str = Query(THEME_DEFAULTS["radius"]),
    epaper: str = Query(THEME_DEFAULTS["epaper"]),
    contrast: str = Query(THEME_DEFAULTS["contrast"]),
    date_style: str = Query(THEME_DEFAULTS["date_style"]),
):
    values = {
        "mode": mode,
        "color": color,
        "font": font,
        "base": base,
        "radius": radius,
        "epaper": "true" if str(epaper).lower() in {"1", "true", "yes", "on"} else "false",
        "contrast": contrast,
        "date_style": date_style,
    }
    return Response(build_user_theme_css(values), media_type="text/css", headers={"Cache-Control": "no-store"})


@router.get("/api/settings/access")
def access_matrix(request: Request, db: Session = Depends(get_db)):
    if not request.session.get("is_admin", False):
        return JSONResponse({"error": "admin required"}, status_code=403)
    return {
        "permissions": [
            {"id": key, **meta}
            for key, meta in PERMISSION_DEFS.items()
        ],
        "users": [
            {
                "id": user.id,
                "username": user.username,
                "is_admin": user.is_admin,
                "permissions": permission_map(user),
            }
            for user in db.query(User).order_by(User.created_at).all()
        ],
    }


@router.post("/api/settings/access/{user_id}")
async def update_access_matrix(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not request.session.get("is_admin", False):
        return JSONResponse({"error": "admin required"}, status_code=403)
    user = db.get(User, user_id)
    if not user:
        return JSONResponse({"error": "user not found"}, status_code=404)
    if user.is_admin:
        return JSONResponse({"error": "Admin accounts always have every permission"}, status_code=400)
    body = await request.json()
    selected = set(body.get("permissions") or []) if isinstance(body, dict) else set()
    values = {key: key in selected for key in PERMISSION_DEFS}
    effective = save_permissions(user, values)
    db.commit()
    return {"ok": True, "user_id": user.id, "permissions": effective}


_NIIM_FIELDS = {
    "url": str,
    "transport": str,
    "address": str,
    "print_task": str,
    "print_direction": str,
    "density": int,
    "label_type": int,
    "dpi": int,
    "max_label_width_mm": float,
    "timeout": float,
}


@router.get("/api/settings/niim")
def niim_settings(request: Request):
    if denied := _deny(request, "printer_settings"):
        return denied
    return {"config": niimblue.config()}


@router.post("/api/settings/niim")
async def save_niim_settings(request: Request, db: Session = Depends(get_db)):
    if denied := _deny(request, "printer_settings"):
        return denied
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON object required"}, status_code=400)
    for field, caster in _NIIM_FIELDS.items():
        if field not in body:
            continue
        try:
            value = caster(body[field])
        except (TypeError, ValueError):
            return JSONResponse({"error": f"Invalid value for {field}"}, status_code=400)
        if field == "transport" and str(value).lower() not in {"ble", "serial"}:
            return JSONResponse({"error": "transport must be ble or serial"}, status_code=400)
        if field == "density" and not 1 <= int(value) <= 5:
            return JSONResponse({"error": "density must be 1–5"}, status_code=400)
        if field == "dpi" and not 100 <= int(value) <= 1200:
            return JSONResponse({"error": "dpi must be 100–1200"}, status_code=400)
        if field in {"max_label_width_mm", "timeout"} and float(value) <= 0:
            return JSONResponse({"error": f"{field} must be positive"}, status_code=400)
        encoded = str(value).lower() if field == "transport" else str(value)
        key = f"niimblue.{field}"
        row = db.get(SystemState, key)
        if row:
            row.value = encoded
        else:
            db.add(SystemState(key=key, value=encoded))
    db.commit()
    return {"ok": True, "config": niimblue.config()}


@router.get("/api/settings/storage")
def storage_status(request: Request):
    if denied := _deny(request, "database_admin"):
        return denied
    return _directory_stats(settings.db_path)


@router.post("/api/settings/pause")
async def capability_pause(request: Request, db: Session = Depends(get_db)):
    if denied := _deny(request, "pause_control"):
        return denied
    from app.events import scan_events
    from app.pause import get_pause_status, pause_until

    body = await request.json()
    try:
        minutes = int(body.get("minutes", 20))
    except (TypeError, ValueError):
        return JSONResponse({"error": "minutes must be numeric"}, status_code=400)
    if not 1 <= minutes <= 1440:
        return JSONResponse({"error": "minutes must be 1–1440"}, status_code=422)
    pause_until(db, minutes)
    status = get_pause_status(db)
    scan_events.publish_threadsafe("pause", status)
    return status


@router.post("/api/settings/resume")
def capability_resume(request: Request, db: Session = Depends(get_db)):
    if denied := _deny(request, "pause_control"):
        return denied
    from app.events import scan_events
    from app.pause import resume_now

    resume_now(db)
    status = {"paused": False, "remaining_seconds": None, "resumes_at": None}
    scan_events.publish_threadsafe("pause", status)
    return status


@router.post("/settings/admin/backup")
def capability_backup(request: Request):
    if denied := _deny(request, "database_admin"):
        return denied
    db_path = settings.db_path
    if not os.path.isfile(db_path):
        return RedirectResponse("/settings?tab=admin", status_code=303)
    backup_path = db_path + ".backup"
    shutil.copy2(db_path, backup_path)
    return FileResponse(
        backup_path,
        media_type="application/octet-stream",
        filename="barcode.db",
        background=BackgroundTask(lambda: os.path.exists(backup_path) and os.unlink(backup_path)),
    )


@router.post("/settings/admin/purge/{table}")
def capability_purge(table: str, request: Request, db: Session = Depends(get_db)):
    if denied := _deny(request, "database_admin"):
        return denied
    table_map = {
        "barcode_cache": BarcodeCache,
        "barcode_mappings": BarcodeMapping,
        "items": Item,
        "activities": Activity,
        "retry_queue": RetryQueue,
    }
    model = table_map.get(table)
    if not model:
        return RedirectResponse("/settings?tab=admin", status_code=303)
    if model is Item:
        db.query(BarcodeMapping).delete()
    db.query(model).delete()
    db.commit()
    return RedirectResponse("/settings?tab=admin", status_code=303)


@router.post("/settings/admin/reset")
def capability_reset(request: Request, db: Session = Depends(get_db)):
    if denied := _deny(request, "database_admin"):
        return denied
    db.query(BarcodeMapping).delete()
    db.query(BarcodeCache).delete()
    db.query(Item).delete()
    db.query(Activity).delete()
    db.query(RetryQueue).delete()
    db.commit()
    return RedirectResponse("/settings?tab=admin", status_code=303)


@router.post("/settings/admin/factory-reset")
def capability_factory_reset(request: Request, db: Session = Depends(get_db)):
    if denied := _deny(request, "database_admin"):
        return denied
    db.query(BarcodeMapping).delete()
    db.query(BarcodeCache).delete()
    db.query(Item).delete()
    db.query(Activity).delete()
    db.query(RetryQueue).delete()
    db.query(ApiToken).delete()
    db.commit()
    return RedirectResponse("/settings?tab=admin", status_code=303)
