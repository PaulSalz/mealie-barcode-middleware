from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.config import settings
from app.models import Action
from app.templating import templates

router = APIRouter()


@router.get("/actions/new", response_class=HTMLResponse)
def action_new_page_v23(request: Request):
    """Home Assistant is the useful default while keeping every field editable."""
    action = Action(
        id="",
        name="",
        action_type="homeassistant",
        webhook_url=settings.ha_webhook_url or "",
        method="POST",
        execution_mode="async",
        payload_json='{"action_id": "", "action_name": "", "barcode": "{{ scan.barcode }}", "kind": "data", "value": "{{ params.value }}"}',
        parameters_json='{"value": "example"}',
    )
    return templates.TemplateResponse(request, "action_detail.html", {
        "action": action,
        "is_new": True,
        "executions": [],
        "stats": {"total": 0, "success": 0, "failed": 0, "ignored": 0, "avg_ms": None, "last_execution": None},
        "id_error": request.query_params.get("error") == "id",
    })
