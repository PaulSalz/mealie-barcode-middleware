from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import SUPPORTED_LANGUAGES, language_for_user, normalize_language, save_language

router = APIRouter()


@router.get("/api/ui-language")
def get_ui_language(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    language = language_for_user(db, user_id, request.session.get("ui_language", "en"))
    request.session["ui_language"] = language
    return {"language": language, "languages": SUPPORTED_LANGUAGES}


@router.post("/api/ui-language")
async def set_ui_language(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "login required"}, status_code=401)
    body = await request.json()
    requested = str(body.get("language") or "")
    language = normalize_language(requested)
    if requested.strip().lower().split("-", 1)[0] not in SUPPORTED_LANGUAGES:
        return JSONResponse({"error": "unsupported language"}, status_code=400)
    save_language(db, user_id, language)
    request.session["ui_language"] = language
    return {"ok": True, "language": language}
