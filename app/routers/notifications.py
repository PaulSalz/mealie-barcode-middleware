from math import ceil

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Activity
from app.templating import _localtime, _relative_time, templates

router = APIRouter()

# Scan outcomes that represent an actual failed/degraded scan. Keep this shared
# semantic for the Activity Errors tab and scanner-health error-scan count.
ERROR_SCAN_RESULTS = ("error", "partial", "broken", "retry_failed", "action_disabled")


@router.get("/api/notifications")
def get_notifications(db: Session = Depends(get_db)):
    items = db.query(Activity).filter(Activity.is_dismissed == False).order_by(Activity.created_at.desc()).limit(50).all()
    return [{
        "id": n.id, "barcode": n.barcode, "title": n.title, "message": n.message,
        "result": n.result, "is_read": n.is_read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    } for n in items]


@router.post("/api/notifications/{notification_id}/read")
def mark_read(notification_id: int, db: Session = Depends(get_db)):
    n = db.get(Activity, notification_id)
    if n:
        n.is_read = True
        db.commit()
    return {"ok": True}


@router.post("/api/notifications/read-all")
def mark_all_read(db: Session = Depends(get_db)):
    db.query(Activity).filter(Activity.is_read == False).update({"is_read": True})
    db.commit()
    return {"ok": True}


@router.post("/api/notifications/read-barcode/{barcode}")
def mark_read_by_barcode(barcode: str, db: Session = Depends(get_db)):
    db.query(Activity).filter(Activity.barcode == barcode, Activity.is_read == False).update({"is_read": True})
    db.commit()
    return {"ok": True}


@router.post("/api/notifications/{notification_id}/dismiss")
def dismiss_notification(notification_id: int, db: Session = Depends(get_db)):
    n = db.get(Activity, notification_id)
    if n:
        n.is_dismissed = True
        n.is_read = True
        db.commit()
    return {"ok": True}


@router.post("/api/notifications/dismiss-read")
def dismiss_all_read(db: Session = Depends(get_db)):
    db.query(Activity).filter(Activity.is_read == True, Activity.is_dismissed == False).update({"is_dismissed": True})
    db.commit()
    return {"ok": True}


def _activity_query(db: Session, result: str):
    query = db.query(Activity)
    if result == "unread":
        query = query.filter(Activity.is_read == False)
    elif result == "added":
        query = query.filter(Activity.result.in_(["added", "added_as_note", "queued"]))
    elif result == "errors":
        query = query.filter(Activity.is_scan_event == True, Activity.result.in_(ERROR_SCAN_RESULTS))
    elif result != "all":
        query = query.filter(Activity.result == result)
    return query


def _page_values(page: int, limit: int) -> tuple[int, int, int]:
    limit = max(1, min(int(limit), 200))
    page = max(1, int(page))
    return page, limit, (page - 1) * limit


@router.get("/activities", response_class=HTMLResponse)
def activity_page(request: Request, result: str = Query("all"), db: Session = Depends(get_db)):
    # The current table widget paginates/sorts these rows client-side. Keep its
    # existing 200-row window until that UI is migrated to server-side paging.
    activities = (
        _activity_query(db, result)
        .order_by(Activity.created_at.desc())
        .limit(200)
        .all()
    )
    return templates.TemplateResponse(request, "activity.html", {
        "activities": activities,
        "current_filter": result,
    })


@router.get("/api/activities")
def get_activities(
    result: str = Query("all"),
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    page, limit, offset = _page_values(page, limit)
    query = _activity_query(db, result)
    count = query.count()
    activities = (
        query.order_by(Activity.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "count": count,
        "page": page,
        "limit": limit,
        "pages": max(1, ceil(count / limit)) if count else 1,
        "items": [{
            "id": a.id, "barcode": a.barcode, "title": a.title, "message": a.message,
            "result": a.result, "is_read": a.is_read,
            "created_at": _relative_time(a.created_at), "created_at_absolute": _localtime(a.created_at),
        } for a in activities],
    }


@router.get("/api/dashboard/frequent")
def dashboard_frequent(db: Session = Depends(get_db)):
    # Reuse the dashboard's canonical aggregation so the live client and initial
    # server render always rank targets identically.
    from app.routers.dashboard import _frequent_targets

    foods, recipes, actions = _frequent_targets(db)
    return {"foods": foods, "recipes": recipes, "actions": actions}


@router.post("/activities/mark-all-read")
def activity_mark_all_read(db: Session = Depends(get_db)):
    db.query(Activity).filter(Activity.is_read == False).update({"is_read": True})
    db.commit()
    return RedirectResponse("/activities", status_code=303)
