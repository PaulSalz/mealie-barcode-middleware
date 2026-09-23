"""Login, logout, first-run account setup, and guided onboarding routes."""
from datetime import timedelta
from urllib.parse import unquote

import bcrypt
from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import language_for_user, normalize_language, save_language
from app.models import Activity, ApiToken, SystemState, User
from app.services.mealie import check_connectivity
from app.services.shopping import get_default_shopping_list_id
from app.templating import templates
from app.utils import utcnow

router = APIRouter()
_MAX_PASSWORD_LENGTH = 128
_ONBOARDING_KEY = "onboarding.completed.v1"


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def _preferred_language(request: Request) -> str:
    return normalize_language(request.headers.get("accept-language", "en"))


def _require_logged_in_admin(request: Request) -> RedirectResponse | None:
    if not request.session.get("user_id"):
        return RedirectResponse("/login?next=/onboarding", status_code=303)
    if not request.session.get("is_admin", False):
        return RedirectResponse("/", status_code=303)
    return None


def _onboarding_status(db: Session) -> dict:
    mealie_ok = check_connectivity()
    default_list_id = get_default_shopping_list_id(db)
    tokens = db.query(ApiToken).filter(ApiToken.scanner_version.isnot(None)).all()
    token_count = db.query(ApiToken.id).count()
    cutoff = utcnow().replace(tzinfo=None) - timedelta(minutes=3)
    disconnected_values = {"", "disconnected", "none", "offline", "unknown"}
    scanner_online = any(
        token.scanner_last_seen_at
        and token.scanner_last_seen_at >= cutoff
        and (token.scanner_device or "").strip().casefold() not in disconnected_values
        for token in tokens
    )
    first_scan = (
        db.query(Activity.id)
        .filter(Activity.is_scan_event == True)
        .order_by(Activity.id.desc())
        .first()
        is not None
    )
    return {
        "mealie_ok": mealie_ok,
        "list_ready": bool(default_list_id),
        "default_list_id": default_list_id,
        "token_ready": token_count > 0,
        "token_count": token_count,
        "scanner_online": scanner_online,
        "first_scan": first_scan,
        "ready_count": sum((mealie_ok, bool(default_list_id), token_count > 0, scanner_online, first_scan)),
        "total_steps": 5,
    }


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = Query("")):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None, "next": next})


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    remember: str = Form(""),
    next: str = Form(""),
    db: Session = Depends(get_db),
):
    if len(password) > _MAX_PASSWORD_LENGTH:
        return templates.TemplateResponse(request, "login.html", {"error": "Invalid username or password", "next": next}, status_code=401)
    user = db.query(User).filter(User.username == username).first()
    if not user:
        bcrypt.checkpw(b"dummy", bcrypt.hashpw(b"dummy", bcrypt.gensalt()))
        return templates.TemplateResponse(request, "login.html", {"error": "Invalid username or password", "next": next}, status_code=401)
    if not _verify_password(password, user.password_hash):
        return templates.TemplateResponse(request, "login.html", {"error": "Invalid username or password", "next": next}, status_code=401)

    language = language_for_user(db, user.id, _preferred_language(request))
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["is_admin"] = user.is_admin
    request.session["ui_language"] = language
    if remember:
        request.session["_remember"] = True
    redirect_to = unquote(next) if next and next.startswith("/") and not next.startswith("//") else "/"
    return RedirectResponse(redirect_to, status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request, db: Session = Depends(get_db)):
    if db.query(User.id).first() is not None:
        return RedirectResponse("/", status_code=303)
    request.session["ui_language"] = _preferred_language(request)
    return templates.TemplateResponse(request, "setup.html", {"error": None})


@router.post("/setup", response_class=HTMLResponse)
def setup_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    if db.query(User.id).first() is not None:
        return RedirectResponse("/", status_code=303)
    errors = []
    username = username.strip()
    if len(username) < 3:
        errors.append("Username must be at least 3 characters.")
    if len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    if len(password) > _MAX_PASSWORD_LENGTH:
        errors.append(f"Password must be at most {_MAX_PASSWORD_LENGTH} characters.")
    if password != password_confirm:
        errors.append("Passwords do not match.")
    if errors:
        return templates.TemplateResponse(request, "setup.html", {"error": " ".join(errors)}, status_code=400)

    user = User(username=username, password_hash=_hash_password(password), is_admin=True)
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        return RedirectResponse("/", status_code=303)

    language = save_language(db, user.id, _preferred_language(request))
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["is_admin"] = user.is_admin
    request.session["ui_language"] = language
    return RedirectResponse("/onboarding", status_code=303)


@router.get("/onboarding", response_class=HTMLResponse)
def onboarding_page(request: Request, db: Session = Depends(get_db)):
    if redirect := _require_logged_in_admin(request):
        return redirect
    return templates.TemplateResponse(request, "onboarding.html", {
        "status": _onboarding_status(db),
        "completed": db.get(SystemState, _ONBOARDING_KEY) is not None,
    })


@router.post("/onboarding/complete")
def onboarding_complete(request: Request, db: Session = Depends(get_db)):
    if redirect := _require_logged_in_admin(request):
        return redirect
    row = db.get(SystemState, _ONBOARDING_KEY)
    if row:
        row.value = "complete"
    else:
        db.add(SystemState(key=_ONBOARDING_KEY, value="complete"))
    db.commit()
    return RedirectResponse("/", status_code=303)
