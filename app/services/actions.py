import json
import logging
import re
import time
from datetime import timedelta
from typing import Any

import httpx

from app.database import SessionLocal
from app.models import Action, ActionExecution
from app.services.action_stats import record_action_result
from app.utils import utcnow

logger = logging.getLogger(__name__)
_TOKEN = re.compile(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}")


def _json(value: str, fallback):
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def _lookup(context: dict[str, Any], path: str):
    current: Any = context
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return ""
        current = current[part]
    return current


def _render(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {str(k): _render(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [_render(v, context) for v in value]
    if not isinstance(value, str):
        return value
    full = _TOKEN.fullmatch(value.strip())
    if full:
        return _lookup(context, full.group(1))
    return _TOKEN.sub(lambda m: str(_lookup(context, m.group(1))), value)


def find_action(db, action_id: str) -> Action | None:
    action = db.get(Action, action_id)
    if action:
        return action
    wanted = action_id.casefold()
    for row in db.query(Action).all():
        aliases = _json(row.aliases_json, [])
        if any(str(alias).casefold() == wanted for alias in aliases):
            return row
    return None


def _result(action: Action, status: str, *, http_status=None, duration_ms=None, error=None) -> dict:
    return {
        "action_id": action.id,
        "action_name": action.name,
        "status": status,
        "http_status": http_status,
        "duration_ms": duration_ms,
        "error": error,
    }


def _create_terminal(db, action: Action, barcode: str, status: str, *, http_status=None, duration_ms=None, error=None) -> dict:
    execution = ActionExecution(
        action_id=action.id,
        barcode=barcode,
        status=status,
        http_status=http_status,
        duration_ms=duration_ms,
        error=error,
    )
    db.add(execution)
    db.flush()
    record_action_result(
        db,
        action.id,
        status,
        duration_ms=duration_ms,
        created_at=execution.created_at,
    )
    db.commit()
    return _result(action, status, http_status=http_status, duration_ms=duration_ms, error=error)


def _finish(db, execution: ActionExecution, action: Action, status: str, *, http_status=None, duration_ms=None, error=None) -> dict:
    execution.status = status
    execution.http_status = http_status
    execution.duration_ms = duration_ms
    execution.error = error
    record_action_result(
        db,
        action.id,
        status,
        duration_ms=duration_ms,
        created_at=execution.created_at,
    )
    db.commit()
    return _result(action, status, http_status=http_status, duration_ms=duration_ms, error=error)


def _retryable(policy: str, *, network_error: bool, status_code: int | None) -> bool:
    if policy == "never":
        return False
    if policy == "network":
        return network_error
    if policy == "5xx":
        return status_code is not None and status_code >= 500
    if policy in ("network_5xx", "network+5xx"):
        return network_error or (status_code is not None and status_code >= 500)
    if policy == "always":
        return network_error or (status_code is not None and status_code >= 400)
    return network_error


def execute_action(action_id: str, barcode: str | None = None, *, force: bool = False) -> dict:
    barcode = barcode or f"ACTION:{action_id}"
    db = SessionLocal()
    execution = None
    try:
        action = find_action(db, action_id)
        if not action:
            return {"action_id": action_id, "status": "not_found", "error": "Action not found"}
        if not action.enabled and not force:
            return _create_terminal(db, action, barcode, "disabled")

        if not force and action.cooldown_seconds > 0:
            latest = (
                db.query(ActionExecution)
                .filter(ActionExecution.action_id == action.id, ActionExecution.status != "ignored_cooldown")
                .order_by(ActionExecution.created_at.desc())
                .first()
            )
            if latest:
                now = utcnow()
                latest_at = latest.created_at
                if latest_at.tzinfo is None:
                    now = now.replace(tzinfo=None)
                if now < latest_at + timedelta(seconds=action.cooldown_seconds):
                    return _create_terminal(db, action, barcode, "ignored_cooldown")

        # Reserve the execution before doing network I/O. This makes async duplicate
        # scans safe: a second background job sees this 'running' row immediately.
        execution = ActionExecution(action_id=action.id, barcode=barcode, status="running")
        db.add(execution)
        db.commit()

        params = _json(action.parameters_json, {})
        context = {
            "action": {"id": action.id, "name": action.name, "type": action.action_type},
            "scan": {"barcode": barcode},
            "params": params,
        }
        payload = _render(_json(action.payload_json, {}), context)
        headers = _render(_json(action.headers_json, {}), context)
        if not isinstance(headers, dict):
            headers = {}
        method = (action.method or "POST").upper()
        timeout = httpx.Timeout(
            connect=max(action.connect_timeout, 0.05),
            read=max(action.read_timeout, 0.05),
            write=max(action.write_timeout, 0.05),
            pool=max(action.pool_timeout, 0.05),
        )

        attempts = max(1, int(action.retries or 0) + 1)
        start = time.monotonic()
        last_error = None
        last_status = None
        for attempt in range(attempts):
            network_error = False
            try:
                kwargs = {"headers": headers, "timeout": timeout}
                if method not in ("GET", "HEAD"):
                    kwargs["json"] = payload
                else:
                    kwargs["params"] = payload if isinstance(payload, dict) else None
                response = httpx.request(method, action.webhook_url, **kwargs)
                last_status = response.status_code
                if response.status_code < 400:
                    duration_ms = int((time.monotonic() - start) * 1000)
                    return _finish(db, execution, action, "success", http_status=response.status_code, duration_ms=duration_ms)
                last_error = f"HTTP {response.status_code}: {response.text[:500]}"
            except httpx.HTTPError as exc:
                network_error = True
                last_error = str(exc)

            if attempt >= attempts - 1 or not _retryable(
                action.retry_policy or "network", network_error=network_error, status_code=last_status
            ):
                break
            delay = max(action.retry_delay, 0) * (max(action.backoff_factor, 0) ** attempt)
            if delay:
                time.sleep(delay)

        duration_ms = int((time.monotonic() - start) * 1000)
        return _finish(db, execution, action, "failed", http_status=last_status, duration_ms=duration_ms, error=last_error)
    except Exception as exc:
        logger.exception("Action execution failed for %s", action_id)
        try:
            action = find_action(db, action_id)
            if execution is not None and action:
                return _finish(db, execution, action, "failed", error=str(exc))
            if action:
                return _create_terminal(db, action, barcode, "failed", error=str(exc))
        except Exception:
            db.rollback()
        return {"action_id": action_id, "status": "failed", "error": str(exc)}
    finally:
        db.close()
