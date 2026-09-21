from __future__ import annotations

import json
import re
from copy import deepcopy

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import SystemState
from app.services.niimblue import (
    connect_printer,
    disconnect_printer,
    is_configured as niim_is_configured,
    print_image_base64,
    printer_rfid,
    printer_status,
)

router = APIRouter()

_PROFILES_KEY = "labels.b21.roll_profiles"
_RFID_BINDINGS_KEY = "labels.b21.rfid_bindings"
_PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

_DEFAULT_PROFILES = [
    {"id": "50x30", "name": "50 × 30 mm", "width_mm": 50.0, "height_mm": 30.0, "dpi": 300, "density": 3, "label_type": 1},
    {"id": "50x25", "name": "50 × 25 mm", "width_mm": 50.0, "height_mm": 25.0, "dpi": 300, "density": 3, "label_type": 1},
    {"id": "40x30", "name": "40 × 30 mm", "width_mm": 40.0, "height_mm": 30.0, "dpi": 300, "density": 3, "label_type": 1},
    {"id": "30x20", "name": "30 × 20 mm", "width_mm": 30.0, "height_mm": 20.0, "dpi": 300, "density": 3, "label_type": 1},
]


def _load_state(db: Session, key: str, default):
    row = db.get(SystemState, key)
    if not row or not row.value:
        return deepcopy(default)
    try:
        return json.loads(row.value)
    except (TypeError, ValueError):
        return deepcopy(default)


def _save_state(db: Session, key: str, value) -> None:
    row = db.get(SystemState, key)
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if row:
        row.value = encoded
    else:
        db.add(SystemState(key=key, value=encoded))
    db.commit()


def _profiles(db: Session) -> list[dict]:
    rows = _load_state(db, _PROFILES_KEY, _DEFAULT_PROFILES)
    if not isinstance(rows, list) or not rows:
        rows = deepcopy(_DEFAULT_PROFILES)
    return rows


def _bindings(db: Session) -> dict[str, str]:
    rows = _load_state(db, _RFID_BINDINGS_KEY, {})
    return rows if isinstance(rows, dict) else {}


def _profile_from_body(body: dict) -> dict:
    profile_id = str(body.get("id") or "").strip()
    name = str(body.get("name") or "").strip()
    if not _PROFILE_ID_RE.fullmatch(profile_id):
        raise ValueError("Profile ID may contain letters, numbers, dot, dash and underscore")
    if not name:
        raise ValueError("Profile name is required")
    try:
        width_mm = float(body.get("width_mm"))
        height_mm = float(body.get("height_mm"))
        dpi = int(body.get("dpi") or 300)
        density = int(body.get("density") or 3)
        label_type = int(body.get("label_type") or 1)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid profile dimensions or printer settings") from exc
    if not 5 <= width_mm <= 100 or not 5 <= height_mm <= 200:
        raise ValueError("Label dimensions are outside the supported editor range")
    if not 100 <= dpi <= 1200:
        raise ValueError("DPI must be between 100 and 1200")
    if not 1 <= density <= 5:
        raise ValueError("Density must be between 1 and 5")
    if label_type < 1:
        raise ValueError("Label type must be positive")
    return {
        "id": profile_id,
        "name": name,
        "width_mm": round(width_mm, 2),
        "height_mm": round(height_mm, 2),
        "dpi": dpi,
        "density": density,
        "label_type": label_type,
    }


@router.get("/labels/b21/status")
def b21_status():
    return printer_status()


@router.post("/labels/b21/connect")
def b21_connect():
    try:
        return connect_printer()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.post("/labels/b21/disconnect")
def b21_disconnect():
    try:
        return disconnect_printer()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.get("/labels/b21/rfid")
def b21_rfid(db: Session = Depends(get_db)):
    try:
        data = printer_rfid()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
    paper = data.get("paperRfidInfo") or {}
    barcode = str(paper.get("barCode") or "")
    bindings = _bindings(db)
    return {
        **data,
        "profile_id": bindings.get(barcode) if barcode else None,
    }


@router.get("/labels/b21/profiles")
def b21_profiles(db: Session = Depends(get_db)):
    return {"profiles": _profiles(db), "rfid_bindings": _bindings(db)}


@router.post("/labels/b21/profiles")
async def b21_save_profile(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    try:
        profile = _profile_from_body(body)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    profiles = _profiles(db)
    replaced = False
    for index, existing in enumerate(profiles):
        if str(existing.get("id")) == profile["id"]:
            profiles[index] = profile
            replaced = True
            break
    if not replaced:
        profiles.append(profile)
    _save_state(db, _PROFILES_KEY, profiles)
    return {"ok": True, "profile": profile, "profiles": profiles}


@router.delete("/labels/b21/profiles/{profile_id}")
def b21_delete_profile(profile_id: str, db: Session = Depends(get_db)):
    profiles = _profiles(db)
    remaining = [profile for profile in profiles if str(profile.get("id")) != profile_id]
    if len(remaining) == len(profiles):
        return JSONResponse({"error": "Profile not found"}, status_code=404)
    if not remaining:
        return JSONResponse({"error": "At least one roll profile is required"}, status_code=400)
    bindings = {barcode: pid for barcode, pid in _bindings(db).items() if pid != profile_id}
    _save_state(db, _PROFILES_KEY, remaining)
    _save_state(db, _RFID_BINDINGS_KEY, bindings)
    return {"ok": True, "profiles": remaining, "rfid_bindings": bindings}


@router.post("/labels/b21/rfid-bind")
async def b21_bind_rfid(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    barcode = str(body.get("barcode") or "").strip()
    profile_id = str(body.get("profile_id") or "").strip()
    if not barcode:
        return JSONResponse({"error": "RFID roll barcode is required"}, status_code=400)
    if not any(str(profile.get("id")) == profile_id for profile in _profiles(db)):
        return JSONResponse({"error": "Roll profile not found"}, status_code=404)
    bindings = _bindings(db)
    bindings[barcode] = profile_id
    _save_state(db, _RFID_BINDINGS_KEY, bindings)
    return {"ok": True, "barcode": barcode, "profile_id": profile_id}


@router.post("/labels/b21/print")
async def b21_print(request: Request):
    body = await request.json()
    image_base64 = str(body.get("image_base64") or "")
    if image_base64.startswith("data:") and "," in image_base64:
        image_base64 = image_base64.split(",", 1)[1]
    if not image_base64:
        return JSONResponse({"error": "Rendered label image is required."}, status_code=400)
    if not niim_is_configured():
        return JSONResponse({"error": "NIIMBOT printing is not configured"}, status_code=400)
    try:
        result = print_image_base64(
            image_base64,
            width_mm=float(body.get("width_mm")),
            height_mm=float(body.get("height_mm")),
            quantity=int(body.get("quantity") or 1),
            density=int(body.get("density") or 3),
            label_type=int(body.get("label_type") or 1),
            dpi=int(body.get("dpi") or 300),
            threshold=int(body.get("threshold") or 128),
        )
        return result
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
