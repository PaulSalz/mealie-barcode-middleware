from fastapi import APIRouter, Depends

from app.auth import require_token
from app.models import ApiToken

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
