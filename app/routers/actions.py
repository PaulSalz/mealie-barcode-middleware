import json
import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Action, ActionExecution
from app.services.actions import execute_action
from app.templating import templates
from app.utils import utcnow

router = APIRouter()
_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,96}$")


def _float(value: str, default: float, minimum: float = 0.0) -> float:
    try:
        return max(float(str(value).replace(",", ".")), minimum)
    except (TypeError, ValueError):
        return default


def _int(value: str, default: int, minimum: int = 0) -> int:
    try:
        return max(int(value), minimum)
    except (TypeError, ValueError):
        return default


def _valid_json(value: str, fallback: str) -> str:
    value = (value or "").strip() or fallback
    try:
        json.loads(value)
        return value
    except ValueError:
        return fallback


def _aliases(value: str) -> str:
    aliases = [a.strip() for a in re.split(r"[,\n]", value or "") if a.strip()]
    aliases = [a for a in aliases if _ID_RE.fullmatch(a)]
    return json.dumps(list(dict.fromkeys(aliases)))


def _apply_form(
    action: Action,
    *,
    name: str,
    description: str,
    aliases: str,
    enabled: bool,
    action_type: str,
    webhook_url: str,
    method: str,
    headers_json: str,
    payload_json: str,
    parameters_json: str,
    connect_timeout: str,
    read_timeout: str,
    write_timeout: str,
    pool_timeout: str,
    retries: str,
    retry_delay: str,
    backoff_factor: str,
    retry_policy: str,
    cooldown_seconds: str,
    execution_mode: str,
    respect_pause: bool,
) -> None:
    action.name = name.strip() or action.id
    action.description = description.strip() or None
    action.aliases_json = _aliases(aliases)
    action.enabled = enabled
    action.action_type = action_type if action_type in {"webhook", "homeassistant"} else "webhook"
    action.webhook_url = webhook_url.strip()
    action.method = method.upper() if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"} else "POST"
    action.headers_json = _valid_json(headers_json, "{}")
    action.payload_json = _valid_json(payload_json, "{}")
    action.parameters_json = _valid_json(parameters_json, "{}")
    action.connect_timeout = _float(connect_timeout, 2.0, 0.05)
    action.read_timeout = _float(read_timeout, 5.0, 0.05)
    action.write_timeout = _float(write_timeout, 5.0, 0.05)
    action.pool_timeout = _float(pool_timeout, 2.0, 0.05)
    action.retries = _int(retries, 0, 0)
    action.retry_delay = _float(retry_delay, 0.5, 0.0)
    action.backoff_factor = _float(backoff_factor, 2.0, 0.0)
    action.retry_policy = retry_policy if retry_policy in {"never", "network", "5xx", "network_5xx", "always"} else "network"
    action.cooldown_seconds = _float(cooldown_seconds, 2.0, 0.0)
    action.execution_mode = execution_mode if execution_mode in {"sync", "async"} else "async"
    action.respect_pause = respect_pause
    action.updated_at = utcnow()


@router.get("/actions", response_class=HTMLResponse)
def actions_page(request: Request, db: Session = Depends(get_db)):
    rows = db.query(Action).order_by(func.lower(Action.name)).all()
    counts = dict(db.query(ActionExecution.action_id, func.count(ActionExecution.id)).group_by(ActionExecution.action_id).all())
    latest_rows = {}
    for execution in db.query(ActionExecution).order_by(ActionExecution.created_at.desc()).all():
        latest_rows.setdefault(execution.action_id, execution)
    return templates.TemplateResponse(request, "actions.html", {
        "actions": rows,
        "counts": counts,
        "latest_rows": latest_rows,
    })


@router.get("/actions/new", response_class=HTMLResponse)
def action_new_page(request: Request):
    action = Action(
        id="",
        name="",
        webhook_url=settings.ha_webhook_url or "",
        payload_json='{"action_id": "{{ action.id }}", "barcode": "{{ scan.barcode }}"}',
        parameters_json='{"duration_seconds": 600}',
    )
    return templates.TemplateResponse(request, "action_detail.html", {"action": action, "is_new": True, "executions": []})


@router.post("/actions/new")
def action_create(
    action_id: str = Form(...), name: str = Form(...), description: str = Form(""), aliases: str = Form(""),
    enabled: bool = Form(False), action_type: str = Form("webhook"), webhook_url: str = Form(...), method: str = Form("POST"),
    headers_json: str = Form("{}"), payload_json: str = Form("{}"), parameters_json: str = Form("{}"),
    connect_timeout: str = Form("2"), read_timeout: str = Form("5"), write_timeout: str = Form("5"), pool_timeout: str = Form("2"),
    retries: str = Form("0"), retry_delay: str = Form("0.5"), backoff_factor: str = Form("2"), retry_policy: str = Form("network"),
    cooldown_seconds: str = Form("2"), execution_mode: str = Form("async"), respect_pause: bool = Form(False),
    db: Session = Depends(get_db),
):
    action_id = action_id.strip()
    if not _ID_RE.fullmatch(action_id) or db.get(Action, action_id):
        return RedirectResponse("/actions/new?error=id", status_code=303)
    action = Action(id=action_id, name=name.strip() or action_id, webhook_url=webhook_url.strip())
    _apply_form(action, name=name, description=description, aliases=aliases, enabled=enabled, action_type=action_type,
                webhook_url=webhook_url, method=method, headers_json=headers_json, payload_json=payload_json,
                parameters_json=parameters_json, connect_timeout=connect_timeout, read_timeout=read_timeout,
                write_timeout=write_timeout, pool_timeout=pool_timeout, retries=retries, retry_delay=retry_delay,
                backoff_factor=backoff_factor, retry_policy=retry_policy, cooldown_seconds=cooldown_seconds,
                execution_mode=execution_mode, respect_pause=respect_pause)
    db.add(action)
    db.commit()
    return RedirectResponse(f"/actions/{quote(action.id, safe='')}?saved=1", status_code=303)


@router.get("/actions/{action_id}", response_class=HTMLResponse)
def action_detail(request: Request, action_id: str, db: Session = Depends(get_db)):
    action = db.get(Action, action_id)
    if not action:
        return templates.TemplateResponse(request, "404.html", {"message": "Action not found"}, status_code=404)
    executions = db.query(ActionExecution).filter(ActionExecution.action_id == action.id).order_by(ActionExecution.created_at.desc()).limit(50).all()
    return templates.TemplateResponse(request, "action_detail.html", {
        "action": action,
        "is_new": False,
        "executions": executions,
        "saved": request.query_params.get("saved") == "1",
    })


@router.post("/actions/{action_id}/edit")
def action_edit(
    action_id: str, name: str = Form(...), description: str = Form(""), aliases: str = Form(""),
    enabled: bool = Form(False), action_type: str = Form("webhook"), webhook_url: str = Form(...), method: str = Form("POST"),
    headers_json: str = Form("{}"), payload_json: str = Form("{}"), parameters_json: str = Form("{}"),
    connect_timeout: str = Form("2"), read_timeout: str = Form("5"), write_timeout: str = Form("5"), pool_timeout: str = Form("2"),
    retries: str = Form("0"), retry_delay: str = Form("0.5"), backoff_factor: str = Form("2"), retry_policy: str = Form("network"),
    cooldown_seconds: str = Form("2"), execution_mode: str = Form("async"), respect_pause: bool = Form(False),
    db: Session = Depends(get_db),
):
    action = db.get(Action, action_id)
    if not action:
        return RedirectResponse("/actions", status_code=303)
    _apply_form(action, name=name, description=description, aliases=aliases, enabled=enabled, action_type=action_type,
                webhook_url=webhook_url, method=method, headers_json=headers_json, payload_json=payload_json,
                parameters_json=parameters_json, connect_timeout=connect_timeout, read_timeout=read_timeout,
                write_timeout=write_timeout, pool_timeout=pool_timeout, retries=retries, retry_delay=retry_delay,
                backoff_factor=backoff_factor, retry_policy=retry_policy, cooldown_seconds=cooldown_seconds,
                execution_mode=execution_mode, respect_pause=respect_pause)
    db.commit()
    return RedirectResponse(f"/actions/{quote(action.id, safe='')}?saved=1", status_code=303)


@router.post("/actions/{action_id}/delete")
def action_delete(action_id: str, db: Session = Depends(get_db)):
    action = db.get(Action, action_id)
    if action:
        db.query(ActionExecution).filter(ActionExecution.action_id == action.id).delete()
        db.delete(action)
        db.commit()
    return RedirectResponse("/actions", status_code=303)


@router.post("/api/actions/{action_id}/test")
def action_test(action_id: str):
    result = execute_action(action_id, f"ACTION:{action_id}", force=True)
    return JSONResponse(result, status_code=200 if result.get("status") == "success" else 502)


@router.get("/actions-search")
def actions_search(q: str = "", db: Session = Depends(get_db)):
    query = db.query(Action).filter(Action.enabled == True)
    if q.strip():
        query = query.filter(Action.name.ilike(f"%{q.strip()}%") | Action.id.ilike(f"%{q.strip()}%"))
    rows = query.order_by(func.lower(Action.name)).limit(30).all()
    return [{"id": a.id, "name": a.name, "code": f"ACTION:{a.id}"} for a in rows]
