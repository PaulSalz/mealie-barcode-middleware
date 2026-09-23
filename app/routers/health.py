from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.mealie_health import mealie_reachable

router = APIRouter()


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    reachable = mealie_reachable()
    status = "ok" if (db_ok and reachable) else "degraded"
    return {
        "status": status,
        "mealie_reachable": reachable,
        "db_ok": db_ok,
    }
