from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.barcode_state import ensure_cache_shell


def recover_known_barcode_cache(request: Request, db: Session = Depends(get_db)) -> None:
    """Self-heal cache identity before rendering a known barcode detail page.

    This dependency is attached to the barcode router. It is intentionally a
    no-op for list/search/mutation routes and replaces the old duplicate
    /barcodes/{barcode} recovery route.
    """
    if request.method != "GET":
        return
    barcode = request.path_params.get("barcode")
    if not barcode:
        return
    ensure_cache_shell(str(barcode), db, only_if_known=True)
