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
    if n: n.is_read = True; db.commit()
    return {"ok": True}


@router.post("/api/notifications/read-all")
def mark_all_read(db: Session = Depends(get_db)):
    db.query(Activity).filter(Activity.is_read == False).update({"is_read": True}); db.commit(); return {"ok": True}


@router.post("/api/notifications/read-barcode/{barcode}")
def mark_read_by_barcode(barcode: str, db: Session = Depends(get_db)):
    db.query(Activity).filter(Activity.barcode == barcode, Activity.is_read == False).update({"is_read": True}); db.commit(); return {"ok": True}


@router.post("/api/notifications/{notification_id}/dismiss")
def dismiss_notification(notification_id: int, db: Session = Depends(get_db)):
    n = db.get(Activity, notification_id)
    if n: n.is_dismissed = True; n.is_read = True; db.commit()
    return {"ok": True}


@router.post("/api/notifications/dismiss-read")
def dismiss_all_read(db: Session = Depends(get_db)):
    db.query(Activity).filter(Activity.is_read == True, Activity.is_dismissed == False).update({"is_dismissed": True}); db.commit(); return {"ok": True}


def _activity_query(db: Session, result: str):
    query = db.query(Activity).order_by(Activity.created_at.desc())
    if result == "unread": query = query.filter(Activity.is_read == False)
    elif result == "added": query = query.filter(Activity.result.in_(["added", "added_as_note", "queued"]))
    elif result == "errors": query = query.filter(Activity.is_scan_event == True, Activity.result.in_(ERROR_SCAN_RESULTS))
    elif result != "all": query = query.filter(Activity.result == result)
    return query


@router.get("/activities", response_class=HTMLResponse)
def activity_page(request: Request, result: str = Query("all"), db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "activity.html", {"activities": _activity_query(db, result).limit(200).all(), "current_filter": result})


@router.get("/api/activities")
def get_activities(result: str = Query("all"), db: Session = Depends(get_db)):
    query = _activity_query(db, result)
    count = query.count()
    activities = query.limit(200).all()
    return {"count": count, "items": [{
        "id": a.id, "barcode": a.barcode, "title": a.title, "message": a.message,
        "result": a.result, "is_read": a.is_read,
        "created_at": _relative_time(a.created_at), "created_at_absolute": _localtime(a.created_at),
    } for a in activities]}


@router.get("/api/dashboard/frequent")
def dashboard_frequent(db: Session = Depends(get_db)):
    # Reuse the dashboard's canonical aggregation so the live client and initial
    # server render always rank targets identically.
    from app.routers.dashboard import _frequent_targets

    foods, recipes, actions = _frequent_targets(db)
    return {"foods": foods, "recipes": recipes, "actions": actions}


@router.post("/activities/mark-all-read")
def activity_mark_all_read(db: Session = Depends(get_db)):
    db.query(Activity).filter(Activity.is_read == False).update({"is_read": True}); db.commit()
    return RedirectResponse("/activities", status_code=303)
