import secrets
from datetime import timedelta

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ApiToken
from app.utils import utcnow


def hash_token(raw_token: str) -> str:
    return bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt()).decode()


def verify_token(raw_token: str, token_hash: str) -> bool:
    return bcrypt.checkpw(raw_token.encode(), token_hash.encode())


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def _header_int(request: Request, name: str) -> int | None:
    value = request.headers.get(name)
    if value is None:
        return None
    try:
        return max(0, int(float(value)))
    except ValueError:
        return None


def _update_scanner_telemetry(request: Request, token: ApiToken, db: Session) -> None:
    version = request.headers.get("X-B2M-Scanner-Version")
    if not version:
        return

    now = utcnow().replace(tzinfo=None)
    last_seen = token.scanner_last_seen_at
    if last_seen is not None and last_seen.tzinfo is not None:
        last_seen = last_seen.replace(tzinfo=None)

    # Physical scans are latency-sensitive. Keep the heavier heartbeat metadata
    # throttled, but always copy the bridge's cumulative scan counter into the
    # shared request session. The scan pipeline already commits an Activity for
    # the scan, so this counter is persisted in that same transaction instead of
    # opening another SQLite writer transaction just for telemetry.
    if request.url.path == "/scan" and last_seen and now - last_seen < timedelta(seconds=15):
        scan_count = _header_int(request, "X-B2M-Scanner-Scans")
        if scan_count is not None:
            token.scanner_total_scans = scan_count
        return

    token.scanner_version = version[:64]
    token.scanner_hostname = (request.headers.get("X-B2M-Scanner-Hostname") or "")[:128] or None
    token.scanner_device = (request.headers.get("X-B2M-Scanner-Device") or "")[:255] or None
    token.scanner_layout = (request.headers.get("X-B2M-Scanner-Layout") or "")[:16] or None
    token.scanner_uptime_seconds = _header_int(request, "X-B2M-Scanner-Uptime")
    token.scanner_total_scans = _header_int(request, "X-B2M-Scanner-Scans")
    token.scanner_errors = _header_int(request, "X-B2M-Scanner-Errors")
    token.scanner_last_latency_ms = _header_int(request, "X-B2M-Scanner-Last-Latency")
    token.scanner_last_seen_at = now
    db.commit()


def _raw_bearer_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    return auth_header.removeprefix("Bearer ").strip()


def require_token(request: Request, db: Session = Depends(get_db)) -> ApiToken:
    raw_token = _raw_bearer_token(request)
    token = _authenticate_raw_token(raw_token, db)
    _update_scanner_telemetry(request, token, db)
    return token


def require_token_no_telemetry(request: Request, db: Session = Depends(get_db)) -> ApiToken:
    """Authenticate a scanner request without another telemetry write.

    The immediate /scanner/received acknowledgement runs concurrently with the
    real /scan request. Writing the same ApiToken row from both requests adds
    avoidable SQLite write contention; the real scan and heartbeat already keep
    scanner telemetry current.
    """
    return _authenticate_raw_token(_raw_bearer_token(request), db)


def verify_psk(device_id: str, db: Session) -> ApiToken:
    if not device_id or not device_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or empty device ID",
        )
    return _authenticate_raw_token(device_id.strip(), db)


def _authenticate_raw_token(raw_token: str, db: Session) -> ApiToken:
    prefix = raw_token[:8]
    candidates = db.query(ApiToken).filter(ApiToken.token_prefix == prefix).all()
    for token in candidates:
        if verify_token(raw_token, token.token_hash):
            return token

    legacy = db.query(ApiToken).filter(ApiToken.token_prefix.is_(None)).all()
    for token in legacy:
        if verify_token(raw_token, token.token_hash):
            token.token_prefix = prefix
            db.commit()
            return token

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid token",
    )
