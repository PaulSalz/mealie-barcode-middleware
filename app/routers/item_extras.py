from __future__ import annotations

from collections import Counter, defaultdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Activity, BarcodeMapping, BarcodeTarget, Item
from app.templating import _localtime, _relative_time

router = APIRouter()


def _item_rows(
    db: Session,
    *,
    q: str = "",
    filter_name: str = "all",
    label: str = "",
    sort: str = "name",
    order: str = "asc",
) -> list[dict]:
    query = db.query(Item)
    if q:
        query = query.filter(Item.name.ilike(f"%{q}%") | Item.aliases.ilike(f"%{q}%"))
    all_items = query.all()

    # Count unique physical barcodes. Primary BarcodeTarget rows mirror
    # BarcodeMapping, so sets avoid double counting them.
    mapped_barcodes: dict[str, set[str]] = defaultdict(set)
    for mapping in db.query(BarcodeMapping).filter(BarcodeMapping.target_type == "food").all():
        mapped_barcodes[mapping.target_id].add(mapping.barcode)
    for target in db.query(BarcodeTarget).filter(
        BarcodeTarget.target_type == "food",
        BarcodeTarget.enabled == True,
    ).all():
        mapped_barcodes[target.target_id].add(target.barcode)

    scan_rows = (
        db.query(Activity.target_id, func.count(Activity.id), func.max(Activity.created_at))
        .filter(Activity.is_scan_event == True, Activity.target_type == "food", Activity.target_id.isnot(None))
        .group_by(Activity.target_id)
        .all()
    )
    scan_counts = {row[0]: int(row[1]) for row in scan_rows}
    last_scans = {row[0]: row[2] for row in scan_rows}

    entries = []
    for item in all_items:
        mapping_count = len(mapped_barcodes.get(item.id, set()))
        scan_count = scan_counts.get(item.id, 0)
        if filter_name == "linked" and mapping_count == 0:
            continue
        if filter_name == "unlinked" and mapping_count > 0:
            continue
        if filter_name == "scanned" and scan_count == 0:
            continue
        if filter_name == "never" and scan_count > 0:
            continue
        if filter_name == "mealie" and item.source != "mealie":
            continue
        if filter_name == "manual" and item.source != "manual":
            continue
        if label and item.label_id != label:
            continue
        entries.append({
            "item": item,
            "mapping_count": mapping_count,
            "scan_count": scan_count,
            "last_scan": last_scans.get(item.id),
        })

    reverse = order == "desc"
    key_map = {
        "name": lambda e: (e["item"].name or "").casefold(),
        "updated": lambda e: e["item"].updated_at or e["item"].created_at,
        "last_scan": lambda e: e["last_scan"] or e["item"].created_at,
        "scans": lambda e: e["scan_count"],
        "barcodes": lambda e: e["mapping_count"],
        "category": lambda e: (e["item"].label_name or "").casefold(),
    }
    entries.sort(key=key_map.get(sort, key_map["name"]), reverse=reverse)
    return entries


@router.get("/api/items-list")
def items_list_api(
    q: str = Query(""),
    sort: str = Query("name"),
    order: str = Query("asc"),
    filter: str = Query("all"),
    label: str = Query(""),
    db: Session = Depends(get_db),
):
    entries = _item_rows(db, q=q, sort=sort, order=order, filter_name=filter, label=label)
    return {
        "items": [
            {
                "id": entry["item"].id,
                "name": entry["item"].name,
                "aliases": entry["item"].aliases or "[]",
                "category": entry["item"].label_name,
                "source": entry["item"].source,
                "mapping_count": entry["mapping_count"],
                "scan_count": entry["scan_count"],
                "last_scan": _relative_time(entry["last_scan"]) if entry["last_scan"] else "Never",
                "last_scan_absolute": _localtime(entry["last_scan"]) if entry["last_scan"] else "",
                "last_scan_sort": entry["last_scan"].timestamp() if entry["last_scan"] else 0,
                "updated": _relative_time(entry["item"].updated_at or entry["item"].created_at),
                "updated_absolute": _localtime(entry["item"].updated_at or entry["item"].created_at),
                "updated_sort": (entry["item"].updated_at or entry["item"].created_at).timestamp(),
            }
            for entry in entries
        ]
    }
