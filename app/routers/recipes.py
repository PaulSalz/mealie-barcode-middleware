from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.config import settings
from app.services.recipes import get_recipe_by_id, normalize_recipe
from app.templating import templates

router = APIRouter()


@router.get("/recipes/{recipe_id}", response_class=HTMLResponse)
def recipe_detail(request: Request, recipe_id: str):
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
    })
