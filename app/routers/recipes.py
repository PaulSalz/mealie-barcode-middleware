import json
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Activity
from app.services.recipes import get_recipe_by_id, normalize_recipe
from app.templating import templates
from app.utils import utcnow

router = APIRouter()


def _activity_contains_recipe(row: Activity, recipe_id: str) -> bool:
    if row.target_type == "recipe" and str(row.target_id or "") == recipe_id:
        return True
    if not row.targets_json:
        return False
    try:
        targets = json.loads(row.targets_json)
    except (TypeError, ValueError):
        return False
    return any(
        str(target.get("type") or target.get("target_type") or "") == "recipe"
        and str(target.get("id") or target.get("target_id") or "") == recipe_id
        for target in targets
        if isinstance(target, dict)
    )


def _recipe_stats(db: Session, recipe_id: str) -> dict:
    scans = (
        db.query(Activity)
        .filter(Activity.is_scan_event == True)
        .order_by(Activity.created_at.desc())
        .all()
    )
    matched = [row for row in scans if _activity_contains_recipe(row, recipe_id)]
    now = utcnow().replace(tzinfo=None)
    return {
        "total": len(matched),
        "days_7": sum(1 for row in matched if row.created_at and row.created_at >= now - timedelta(days=7)),
        "days_30": sum(1 for row in matched if row.created_at and row.created_at >= now - timedelta(days=30)),
        "last_scan": matched[0].created_at if matched else None,
    }


@router.get("/recipes/{recipe_id}", response_class=HTMLResponse)
def recipe_detail(request: Request, recipe_id: str, db: Session = Depends(get_db)):
    raw = get_recipe_by_id(recipe_id)
    if not raw:
        return templates.TemplateResponse(
            request,
            "404.html",
            {"message": "Recipe not found in Mealie"},
            status_code=404,
        )
    return templates.TemplateResponse(request, "recipe_detail.html", {
        "recipe": normalize_recipe(raw),
        "mealie_url": settings.mealie_url.rstrip("/"),
        "stats": _recipe_stats(db, recipe_id),
    })
