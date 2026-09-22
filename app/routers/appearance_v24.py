from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import SystemState
from app.theme import COLOR_CSS

router = APIRouter()

_DEFAULT = "smooth"
_ALLOWED = {_DEFAULT, *COLOR_CSS.keys()}


def _key(user_id: int) -> str:
    return f"appearance.v24.user.{int(user_id)}.rainbow_buttons"


def _current_user_id(request: Request) -> int | None:
    value = request.session.get("user_id")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _read(db: Session, user_id: int) -> str:
    row = db.get(SystemState, _key(user_id))
    value = str(row.value).strip().lower() if row and row.value else _DEFAULT
    return value if value in _ALLOWED else _DEFAULT


@router.get("/api/appearance-v24")
def appearance_v24_get(request: Request, db: Session = Depends(get_db)):
    user_id = _current_user_id(request)
    if user_id is None:
        return JSONResponse({"error": "login required"}, status_code=401)
    return {
        "rainbow_buttons": _read(db, user_id),
        "choices": [_DEFAULT, *COLOR_CSS.keys()],
    }


@router.post("/api/appearance-v24")
async def appearance_v24_save(request: Request, db: Session = Depends(get_db)):
    user_id = _current_user_id(request)
    if user_id is None:
        return JSONResponse({"error": "login required"}, status_code=401)
    body = await request.json()
    value = str(body.get("rainbow_buttons", _DEFAULT)).strip().lower() if isinstance(body, dict) else _DEFAULT
    if value not in _ALLOWED:
        return JSONResponse({"error": "invalid rainbow_buttons value"}, status_code=400)
    row = db.get(SystemState, _key(user_id))
    if row:
        row.value = value
    else:
        db.add(SystemState(key=_key(user_id), value=value))
    db.commit()
    return {"ok": True, "rainbow_buttons": value}
