from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_token
from app.database import get_db
from app.models import ApiToken
from app.templating import _localtime, _relative_time
from app.utils import utcnow

router = APIRouter()


@router.post("/scanner/heartbeat")
def scanner_heartbeat(token: ApiToken = Depends(require_token)):
    """Authenticated no-op endpoint; require_token stores scanner telemetry headers."""
    return {
        "ok": True,
        "token": token.name,
        "scanner_version": token.scanner_version,
        "last_seen": token.scanner_last_seen_at.isoformat() if token.scanner_last_seen_at else None,
    }


@router.get("/api/scanners")
def scanner_health(db: Session = Depends(get_db)):
    """Session-protected scanner telemetry grouped by the API token that reported it."""
    now = utcnow().replace(tzinfo=None)
    rows = db.query(ApiToken).order_by(ApiToken.name).all()
    scanners = []
    for token in rows:
        if not token.scanner_version:
            continue
        last_seen = token.scanner_last_seen_at
        online = bool(last_seen and last_seen >= now - timedelta(minutes=3))
        scanners.append({
            "token_id": token.id,
            "token_name": token.name,
            "token_prefix": token.token_prefix,
            "version": token.scanner_version,
            "hostname": token.scanner_hostname,
            "device": token.scanner_device,
            "layout": token.scanner_layout,
            "online": online,
            "last_seen": _relative_time(last_seen),
            "last_seen_absolute": _localtime(last_seen),
            "uptime_seconds": token.scanner_uptime_seconds or 0,
            "scans": token.scanner_total_scans or 0,
            "errors": token.scanner_errors or 0,
            "latency_ms": token.scanner_last_latency_ms,
        })
    return {"items": scanners}
