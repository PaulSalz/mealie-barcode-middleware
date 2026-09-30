import logging
import os
from datetime import datetime

import bcrypt
from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.auth import generate_token, hash_token
from app.access_v23 import has_permission
from app.config import settings, EDITABLE_SETTINGS, READONLY_SETTINGS
from app.database import get_db
from app.models import ApiToken, BarcodeCache, BarcodeMapping, Item, Activity, RetryQueue, SystemState, User
from app.services.homeassistant import build_scan_notification_automation, homeassistant_webhook_id
from app.templating import templates, set_cached_theme, get_cached_theme_css
from app.theme import THEME_CHOICES, THEME_DEFAULTS, get_theme, save_theme

logger = logging.getLogger(__name__)
router = APIRouter()

_GROUP_ORDER = [
    "Mealie Connection",
    "Home Assistant",
    "Barcode Lookup Sources",
    "Matching & Sync",
    "Scanning",
    "System",
]

_TAB_DESCRIPTIONS = {
    "mealie": "Connection details for your Mealie instance. Configured via environment variables.",
    "homeassistant": "Push notifications and deep links via Home Assistant webhooks.",
    "lookup": "Configure which product databases to query and how they interact.",
    "matching": "Control how scanned products are matched and synced with Mealie.",
    "scanning": "What happens when a barcode is scanned — unknown barcode handling and list pause controls.",
    "system": "Timezone, logging, and other system-level settings.",
    "printer": "Connect or disconnect the B21 label printer and open label printing.",
    "appearance": "Customize the look and feel of the web dashboard.",
    "tokens": "API tokens for authenticating barcode scanners.",
    "users": "Manage user accounts for the web dashboard.",
    "admin": "Backup, purge, or reset the application database.",
}

_SECTION_DESCRIPTIONS = {
    "Strategy": "Control how multiple data sources work together.",
    "Fuzzy Matching": "How product names are compared against your Mealie food catalog.",
    "Scheduling & Retry": "How often data is refreshed and how failures are handled.",
    "Unknown & Unlinked Barcodes": "What happens when a scanned barcode can't be matched to a Mealie item.",
    "Notifications": "Send push notifications to your phone when a scanned item needs attention.",
    "Infrastructure": "Set via environment variables — not editable here.",
}


def _build_config_groups():
    """Build config groups with section sub-grouping for the template."""
    group_items: dict[str, list] = {g: [] for g in _GROUP_ORDER}
    for key, meta in EDITABLE_SETTINGS.items():
        group = meta["group"]
        val = settings.get_display_value(key)
        env_default = str(settings.get_env_default(key))
        if meta["type"] == "choice":
            valid_values = [
                choice[0] if isinstance(choice, (tuple, list)) else choice
                for choice in meta.get("choices", [])
            ]
            if val not in valid_values:
                val = valid_values[0] if valid_values else ""
            if env_default not in valid_values:
                env_default = valid_values[0] if valid_values else ""
        overridden = settings.is_overridden(key)
        group_items.setdefault(group, []).append({
            "key": meta["label"], "field": key, "value": val,
            "description": meta["description"], "hint": meta.get("hint"),
            "help": meta.get("help"), "form_label": meta.get("form_label"),
            "editable": True, "overridden": overridden, "env_default": env_default,
            "type": meta["type"], "choices": meta.get("choices"),
            "min": meta.get("min"), "max": meta.get("max"),
            "wide": meta.get("wide", False), "section": meta.get("section", ""),
        })
    for key, meta in READONLY_SETTINGS.items():
        group = meta["group"]
        if meta.get("secret"):
            val = "***" if getattr(settings, key) else "(not set)"
        else:
            val = getattr(settings, key)
            val = "(not set)" if val is None or val == "" else str(val)
        group_items.setdefault(group, []).append({
            "key": meta["label"], "field": key, "value": val,
            "description": meta["description"], "hint": meta.get("hint"),
            "help": meta.get("help"), "editable": False,
            "section": meta.get("section", ""),
        })
    result = []
    for group_name in _GROUP_ORDER:
        items = group_items.get(group_name)
        if not items:
            continue
        section_map: dict[str, list] = {}
        section_order: list[str] = []
        for item in items:
            section = item["section"]
            if section not in section_map:
                section_map[section] = []
                section_order.append(section)
            section_map[section].append(item)
        result.append((group_name, [(s, section_map[s]) for s in section_order]))
    return result


_TABS = [
    ("mealie", "Mealie", "ti-plug"),
    ("homeassistant", "Home Assistant", "ti-home"),
    ("lookup", "Barcode Lookup", "ti-barcode"),
    ("matching", "Matching & Sync", "ti-arrows-sort"),
    ("scanning", "Scanning", "ti-scan"),
    ("printer", "Label Printer", "ti-printer"),
    ("system", "System", "ti-settings"),
    ("appearance", "Appearance", "ti-palette"),
    ("tokens", "API Tokens", "ti-key"),
    ("users", "Users", "ti-users"),
    ("admin", "Database", "ti-database"),
]

_SIDEBAR_GROUPS = {
    "Integrations": ["mealie", "homeassistant"],
    "Configuration": ["lookup", "matching", "scanning", "system"],
    "Printing": ["printer"],
    "Personalization": ["appearance"],
    "Security": ["tokens", "users"],
    "Administration": ["admin"],
}

_TAB_GROUPS = {
    "mealie": ["Mealie Connection"],
    "homeassistant": ["Home Assistant"],
    "lookup": ["Barcode Lookup Sources"],
    "matching": ["Matching & Sync"],
    "scanning": ["Scanning"],
    "system": ["System"],
}

_TAB_PERMISSIONS = {
    "mealie": "configuration",
    "homeassistant": "configuration",
    "lookup": "configuration",
    "matching": "configuration",
    "scanning": "configuration",
    "system": "configuration",
    "printer": "printer",
    "tokens": "tokens",
    "users": "users",
    "admin": "database",
}


def _allowed(request: Request, db: Session, permission: str) -> bool:
    return has_permission(db, request.session.get("user_id"), permission)


def _require_permission(request: Request, db: Session, permission: str) -> RedirectResponse | None:
    if _allowed(request, db, permission):
        return None
    return RedirectResponse(f"/?permission_denied={permission}", status_code=303)


def _visible_settings_tabs(request: Request, db: Session):
    tabs = [
        tab for tab in _TABS
        if _TAB_PERMISSIONS.get(tab[0]) and _allowed(request, db, _TAB_PERMISSIONS[tab[0]])
    ]
    tab_ids = {tab[0] for tab in tabs}
    groups = {
        label: [tab_id for tab_id in group_ids if tab_id in tab_ids]
        for label, group_ids in _SIDEBAR_GROUPS.items()
    }
    return tabs, {label: tab_ids for label, tab_ids in groups.items() if tab_ids}


def _require_admin(request: Request, db: Session) -> RedirectResponse | None:
    user = db.get(User, request.session.get("user_id"))
    if not user or not user.is_admin:
        return RedirectResponse("/", status_code=303)
    return None


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, tab: str = Query("mealie"), db: Session = Depends(get_db)):
    tabs, sidebar_groups = _visible_settings_tabs(request, db)
    permission = _TAB_PERMISSIONS.get(tab)
    if not permission or not _allowed(request, db, permission):
        if tab == "mealie" and tabs:
            tab = tabs[0][0]
            permission = _TAB_PERMISSIONS.get(tab)
        if not permission or not _allowed(request, db, permission):
            return RedirectResponse("/?permission_denied=" + str(permission or "settings"), status_code=303)
    all_groups = _build_config_groups()
    active_groups = _TAB_GROUPS.get(tab, [])
    tab_groups = [(name, sections) for name, sections in all_groups if name in active_groups]
    has_editable = any(item["editable"] for _, sections in tab_groups for _, items in sections for item in items)
    tokens = db.query(ApiToken).order_by(ApiToken.created_at.desc()).all() if tab == "tokens" else []
    theme = get_theme(db) if tab == "appearance" else {}
    users = db.query(User).order_by(User.created_at).all() if tab == "users" else []
    admin_info = _get_admin_info(db) if tab == "admin" else {}
    tab_label = next((label for tid, label, _ in _TABS if tid == tab), tab.title())
    return templates.TemplateResponse(request, "settings.html", {
        "tabs": tabs, "sidebar_groups": sidebar_groups,
        "current_tab": tab, "current_tab_label": tab_label,
        "tab_description": _TAB_DESCRIPTIONS.get(tab, ""),
        "section_descriptions": _SECTION_DESCRIPTIONS,
        "config_groups": tab_groups, "has_editable": has_editable,
        "tokens": tokens, "new_token": None, "users": users,
        "is_admin": bool(db.get(User, request.session.get("user_id")) and db.get(User, request.session.get("user_id")).is_admin),
        "theme": theme, "theme_choices": THEME_CHOICES, "admin_info": admin_info,
        "scan_notification_automation": build_scan_notification_automation(settings.ha_webhook_url) if tab == "homeassistant" else "",
        "scan_webhook_configured": bool(homeassistant_webhook_id(settings.ha_webhook_url)) if tab == "homeassistant" else False,
    })


@router.post("/settings/configuration", response_class=HTMLResponse)
async def save_settings(request: Request, db: Session = Depends(get_db)):
    if redirect := _require_permission(request, db, "configuration"):
        return redirect
    form_data = await request.form()
    tab = form_data.get("_tab", "mealie")
    tab_group_names = _TAB_GROUPS.get(tab, [])
    changed = []
    for key, meta in EDITABLE_SETTINGS.items():
        if meta["group"] not in tab_group_names:
            continue
        form_key = f"setting_{key}"
        if meta["type"] == "bool":
            new_val = "true" if form_key in form_data else "false"
        else:
            new_val = form_data.get(form_key)
            if new_val is None:
                continue
        new_val = new_val.strip()
        if new_val != settings.get_display_value(key):
            try:
                settings.save_override(key, new_val, db)
                changed.append(key)
            except ValueError as exc:
                logger.warning("Invalid setting %s=%s: %s", key, new_val, exc)
    if changed:
        logger.info("Settings updated via UI: %s", ", ".join(changed))
    return RedirectResponse(f"/settings?tab={tab}&saved=1", status_code=303)


@router.post("/settings/configuration/{field}/reset")
def reset_setting(field: str, request: Request, db: Session = Depends(get_db)):
    if redirect := _require_permission(request, db, "configuration"):
        return redirect
    if field not in EDITABLE_SETTINGS:
        return RedirectResponse("/settings?tab=mealie", status_code=303)
    group = EDITABLE_SETTINGS[field].get("group", "")
    tab = next((tab_id for tab_id, groups in _TAB_GROUPS.items() if group in groups), "mealie")
    settings.reset_override(field, db)
    logger.info("Setting '%s' reset to env default via UI", field)
    return RedirectResponse(f"/settings?tab={tab}&saved=1", status_code=303)


@router.post("/settings/tokens/create", response_class=HTMLResponse)
def create_token(request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    if redirect := _require_permission(request, db, "tokens"):
        return redirect
    raw = generate_token()
    token = ApiToken(name=name, token_hash=hash_token(raw), token_prefix=raw[:8])
    db.add(token)
    db.commit()
    db.refresh(token)
    tokens = db.query(ApiToken).order_by(ApiToken.created_at.desc()).all()
    return templates.TemplateResponse(request, "settings.html", {
        "tabs": _TABS, "sidebar_groups": _SIDEBAR_GROUPS, "config_groups": [],
        "tokens": tokens, "current_tab": "tokens", "current_tab_label": "API Tokens",
        "tab_description": _TAB_DESCRIPTIONS.get("tokens", ""),
        "section_descriptions": _SECTION_DESCRIPTIONS, "new_token": raw,
        "is_admin": bool(db.get(User, request.session.get("user_id")) and db.get(User, request.session.get("user_id")).is_admin),
        "new_token_name": name, "theme": {}, "theme_choices": THEME_CHOICES,
    })


@router.post("/settings/tokens/{token_id}/delete")
def delete_token(token_id: str, request: Request, db: Session = Depends(get_db)):
    if redirect := _require_permission(request, db, "tokens"):
        return redirect
    token = db.get(ApiToken, token_id)
    if token:
        db.delete(token)
        db.commit()
    return RedirectResponse("/settings?tab=tokens", status_code=303)


@router.get("/api/settings/pause-status")
def api_pause_status(db: Session = Depends(get_db)):
    from app.pause import get_pause_status
    return JSONResponse(get_pause_status(db))


@router.post("/api/settings/pause")
async def api_pause(request: Request, db: Session = Depends(get_db)):
    if not _allowed(request, db, "scanning"):
        return JSONResponse({"error": "scanning permission required"}, status_code=403)
    from app.events import scan_events
    from app.pause import get_pause_status, pause_until
    body = await request.json()
    minutes = int(body.get("minutes", 20))
    if minutes < 1 or minutes > 1440:
        return JSONResponse({"error": "minutes must be 1–1440"}, status_code=422)
    pause_until(db, minutes)
    status = get_pause_status(db)
    scan_events.publish_threadsafe("pause", status)
    return JSONResponse(status)


@router.post("/api/settings/resume")
def api_resume(request: Request, db: Session = Depends(get_db)):
    if not _allowed(request, db, "scanning"):
        return JSONResponse({"error": "scanning permission required"}, status_code=403)
    from app.events import scan_events
    from app.pause import resume_now
    resume_now(db)
    scan_events.publish_threadsafe("pause", {"paused": False, "remaining_seconds": None, "resumes_at": None})
    return JSONResponse({"paused": False})


@router.get("/theme.css")
def theme_css():
    return Response(content=get_cached_theme_css(), media_type="text/css", headers={"Cache-Control": "no-cache"})


@router.get("/api/theme")
def api_get_theme(db: Session = Depends(get_db)):
    return JSONResponse(get_theme(db))


@router.post("/api/theme/mode")
async def api_set_theme_mode(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    current = get_theme(db)
    current["mode"] = body.get("mode", "light")
    save_theme(db, current)
    set_cached_theme(get_theme(db))
    return JSONResponse({"ok": True})


@router.post("/settings/theme")
async def save_theme_settings(request: Request, db: Session = Depends(get_db)):
    if redirect := _require_admin(request, db):
        return redirect
    form_data = await request.form()
    values = {
        "mode": form_data.get("theme_mode", THEME_DEFAULTS["mode"]),
        "color": form_data.get("theme_color", THEME_DEFAULTS["color"]),
        "font": form_data.get("theme_font", THEME_DEFAULTS["font"]),
        "base": form_data.get("theme_base", THEME_DEFAULTS["base"]),
        "radius": form_data.get("theme_radius", THEME_DEFAULTS["radius"]),
    }
    save_theme(db, values)
    set_cached_theme(get_theme(db))
    return RedirectResponse("/settings?tab=appearance&saved=1", status_code=303)


def _get_admin_info(db: Session) -> dict:
    db_path = settings.db_path
    try:
        file_size = os.path.getsize(db_path)
        modified_at = datetime.fromtimestamp(os.path.getmtime(db_path))
    except OSError:
        file_size = 0
        modified_at = None

    last_backup = db.get(SystemState, "maintenance.last_verified_backup")
    last_verified_backup = None
    if last_backup and last_backup.value:
        try:
            last_verified_backup = datetime.fromisoformat(last_backup.value)
        except (TypeError, ValueError):
            logger.warning("Invalid last verified backup timestamp: %r", last_backup.value)

    return {
        "db_path": db_path,
        "file_size": file_size,
        "modified_at": modified_at,
        "last_verified_backup": last_verified_backup,
        "tables": {
            "barcode_cache": db.query(BarcodeCache).count(),
            "barcode_mappings": db.query(BarcodeMapping).count(),
            "items": db.query(Item).count(),
            "activities": db.query(Activity).count(),
            "retry_queue": db.query(RetryQueue).count(),
            "api_tokens": db.query(ApiToken).count(),
        },
    }


# /settings/admin/backup is intentionally owned by app.routers.database_backup.
# Keeping a second implementation here previously made it possible to regress to
# a raw file copy that omitted SQLite WAL contents.


@router.post("/settings/admin/purge/{table}")
def admin_purge_table(table: str, request: Request, db: Session = Depends(get_db)):
    if not _allowed(request, db, "database"):
        return RedirectResponse("/settings?tab=mealie", status_code=303)
    table_map = {
        "barcode_cache": BarcodeCache, "barcode_mappings": BarcodeMapping,
        "items": Item, "activities": Activity, "retry_queue": RetryQueue,
    }
    model = table_map.get(table)
    if not model:
        return RedirectResponse("/settings?tab=admin", status_code=303)
    if model is Item:
        db.query(BarcodeMapping).delete()
    db.query(model).delete()
    db.commit()
    logger.info("Admin: purged table '%s'", table)
    return RedirectResponse("/settings?tab=admin", status_code=303)


@router.post("/settings/admin/reset")
def admin_reset(request: Request, db: Session = Depends(get_db)):
    if not _allowed(request, db, "database"):
        return RedirectResponse("/settings?tab=mealie", status_code=303)
    db.query(BarcodeMapping).delete()
    db.query(BarcodeCache).delete()
    db.query(Item).delete()
    db.query(Activity).delete()
    db.query(RetryQueue).delete()
    db.commit()
    logger.info("Admin: full data reset (tokens preserved)")
    return RedirectResponse("/settings?tab=admin", status_code=303)


@router.post("/settings/admin/factory-reset")
def admin_factory_reset(request: Request, db: Session = Depends(get_db)):
    if not _allowed(request, db, "database"):
        return RedirectResponse("/settings?tab=mealie", status_code=303)
    db.query(BarcodeMapping).delete()
    db.query(BarcodeCache).delete()
    db.query(Item).delete()
    db.query(Activity).delete()
    db.query(RetryQueue).delete()
    db.query(ApiToken).delete()
    db.commit()
    logger.info("Admin: factory reset — all data deleted")
    return RedirectResponse("/settings?tab=admin", status_code=303)


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except (ValueError, TypeError):
        return False


def _current_user_password_matches(request: Request, password: str, db: Session) -> bool:
    user_id = request.session.get("user_id")
    user = db.get(User, user_id) if user_id is not None else None
    return bool(user and _verify_password(password, user.password_hash))


def _users_redirect(status: str) -> RedirectResponse:
    return RedirectResponse(f"/settings?tab=users&user_status={status}", status_code=303)


@router.post("/settings/users/add")
def add_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    is_admin: str = Form(""),
    admin_current_password: str = Form(""),
    db: Session = Depends(get_db),
):
    if not _allowed(request, db, "users"):
        return RedirectResponse("/settings?tab=mealie", status_code=303)
    username = username.strip()
    if len(username) < 3:
        return _users_redirect("invalid_username")
    if len(password) < 8 or len(password) > 128:
        return _users_redirect("invalid_password")
    grant_admin = is_admin.strip().lower() in {"1", "true", "on"}
    actor = db.get(User, request.session.get("user_id"))
    if grant_admin and not (actor and actor.is_admin):
        return _users_redirect("admin_required")
    if grant_admin and not admin_current_password:
        return _users_redirect("admin_password_required")
    if grant_admin and not _current_user_password_matches(request, admin_current_password, db):
        return _users_redirect("admin_password_invalid")
    if db.query(User).filter(User.username == username).first():
        return _users_redirect("username_taken")
    db.add(User(username=username, password_hash=_hash_password(password), is_admin=grant_admin))
    db.commit()
    logger.info("User created: %s (admin=%s)", username, grant_admin)
    return _users_redirect("user_created")


@router.post("/settings/users/{user_id}/delete")
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not _allowed(request, db, "users"):
        return RedirectResponse("/settings?tab=mealie", status_code=303)
    if user_id == request.session.get("user_id"):
        return RedirectResponse("/settings?tab=users", status_code=303)
    user = db.get(User, user_id)
    actor = db.get(User, request.session.get("user_id"))
    if user and user.is_admin and not (actor and actor.is_admin):
        return _users_redirect("admin_required")
    if user:
        logger.info("User deleted: %s", user.username)
        db.delete(user)
        db.commit()
    return RedirectResponse("/settings?tab=users", status_code=303)


@router.post("/settings/users/{user_id}/password")
def change_password(
    user_id: int,
    request: Request,
    current_password: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    current_user_id = request.session.get("user_id")
    actor = db.get(User, current_user_id) if current_user_id is not None else None
    is_admin = bool(actor and actor.is_admin)
    if not is_admin and user_id != current_user_id:
        return _users_redirect("access_denied")
    if len(password) < 8 or len(password) > 128:
        return _users_redirect("invalid_password")
    if password != password_confirm:
        return _users_redirect("password_mismatch")
    if not _current_user_password_matches(request, current_password, db):
        return _users_redirect("current_password_invalid")
    user = db.get(User, user_id)
    if not user:
        return _users_redirect("user_not_found")
    user.password_hash = _hash_password(password)
    db.commit()
    logger.info("Password changed for user: %s", user.username)
    return _users_redirect("password_changed")
