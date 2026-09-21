import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import BarcodeCache
from app.utils import utcnow

logger = logging.getLogger(__name__)

_LOOKUP_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="barcode-lookup")
_LOOKUP_TIMEOUT = httpx.Timeout(3.0, connect=1.0)
_LOOKUP_BUDGET_SECONDS = 3.25
_http = httpx.Client(
    limits=httpx.Limits(max_connections=12, max_keepalive_connections=6, keepalive_expiry=60.0),
)


def lookup_openfoodfacts(barcode: str) -> dict | None:
    """Query OpenFoodFacts. Returns product dict or None."""
    if not settings.off_enabled:
        return None
    url = f"{settings.off_url_base}{barcode}.json"
    try:
        resp = _http.get(url, timeout=_LOOKUP_TIMEOUT)
        logger.info("OpenFoodFacts %s: HTTP %s", barcode, resp.status_code)
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("status") != 1:
            return None
        product = data.get("product", {})
        name = product.get("product_name") or ""
        if not name.strip():
            return None
        return {
            "title": name.strip(),
            "brand": (product.get("brands") or "").split(",")[0].strip(),
            "product_type": (product.get("product_type") or "").split(",")[0].strip() or None,
            "quantity": (product.get("quantity") or "").strip() or None,
            "source": "openfoodfacts",
        }
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("OpenFoodFacts error for %s: %s", barcode, exc)
        return None


def lookup_upcdatabase(barcode: str) -> dict | None:
    """Query UPCDatabase. Returns product dict or None."""
    if not settings.upcdb_enabled or not settings.upcdb_api_key:
        return None
    url = f"{settings.upcdb_url_base}{barcode}"
    try:
        resp = _http.get(url, params={"apikey": settings.upcdb_api_key}, timeout=_LOOKUP_TIMEOUT)
        logger.info("UPCDatabase %s: HTTP %s", barcode, resp.status_code)
        if resp.status_code != 200:
            return None
        text = resp.text
        match = re.search(r'\{\s*"', text)
        if not match:
            logger.warning("UPCDatabase %s: no JSON object found in response", barcode)
            return None
        clean = text[match.start():]
        try:
            data = json.loads(clean)
        except json.JSONDecodeError:
            logger.warning("UPCDatabase %s: failed to parse extracted JSON", barcode)
            return None
        if not data.get("success"):
            return None
        title = data.get("title") or data.get("alias") or data.get("description") or ""
        if not title.strip():
            return None
        metadata = data.get("metadata") or {}
        return {
            "title": title.strip(),
            "brand": (data.get("brand") or "").split(",")[0].strip(),
            "product_type": (data.get("category") or "").split(",")[0].strip().lower() or None,
            "quantity": (metadata.get("quantity") or "").split(",")[0].strip() or None,
            "source": "upcdatabase",
        }
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("UPCDatabase error for %s: %s", barcode, exc)
        return None


def _get_lookup_functions() -> tuple:
    """Return (primary_fn, secondary_fn) based on LOOKUP_PRIMARY config."""
    off_fn = lookup_openfoodfacts if settings.off_enabled else None
    upcdb_fn = lookup_upcdatabase if settings.upcdb_enabled and settings.upcdb_api_key else None
    if settings.lookup_primary == "upcdb":
        primary, secondary = upcdb_fn, off_fn
    else:
        primary, secondary = off_fn, upcdb_fn
    if primary is None:
        primary, secondary = secondary, None
    return primary, secondary


def _result_has_gaps(result: dict) -> bool:
    return not all(result.get(field) for field in ("brand", "quantity", "product_type"))


def _merge_gaps(base: dict, supplement: dict) -> bool:
    changed = False
    for field in ("brand", "quantity", "product_type"):
        if not base.get(field) and supplement.get(field):
            base[field] = supplement[field]
            changed = True
    if changed:
        base["source"] = f"{base['source']}+{supplement['source']}"
    return changed


def _lookup_with_budget(barcode: str, primary_fn, secondary_fn) -> tuple[dict | None, dict | None]:
    """Run providers concurrently so failover latency is bounded by one provider timeout."""
    started = time.monotonic()
    if primary_fn is None:
        return None, None
    if secondary_fn is None:
        return primary_fn(barcode), None

    primary_future = _LOOKUP_POOL.submit(primary_fn, barcode)
    secondary_future = _LOOKUP_POOL.submit(secondary_fn, barcode)
    primary_result = None
    secondary_result = None
    try:
        primary_result = primary_future.result(timeout=_LOOKUP_BUDGET_SECONDS)
    except FutureTimeoutError:
        logger.warning("Primary barcode lookup exceeded %.2fs for %s", _LOOKUP_BUDGET_SECONDS, barcode)
    except Exception:
        logger.exception("Primary barcode lookup failed for %s", barcode)

    if not primary_result or (
        settings.lookup_strategy == "complement"
        and not settings.lookup_enrich_in_background
        and _result_has_gaps(primary_result)
    ):
        remaining = max(0.05, _LOOKUP_BUDGET_SECONDS - (time.monotonic() - started))
        try:
            secondary_result = secondary_future.result(timeout=remaining)
        except FutureTimeoutError:
            logger.warning("Secondary barcode lookup exceeded remaining scan budget for %s", barcode)
        except Exception:
            logger.exception("Secondary barcode lookup failed for %s", barcode)

    elapsed_ms = int((time.monotonic() - started) * 1000)
    if elapsed_ms >= 1000:
        logger.warning("Barcode lookup %s took %d ms", barcode, elapsed_ms)
    return primary_result, secondary_result


def perform_lookup(barcode: str, db: Session) -> BarcodeCache:
    """Lookup a barcode with a bounded hot-path latency and upsert the cache."""
    primary_fn, secondary_fn = _get_lookup_functions()
    primary_result, secondary_result = _lookup_with_budget(barcode, primary_fn, secondary_fn)
    result = primary_result or secondary_result
    if (
        result
        and primary_result
        and settings.lookup_strategy == "complement"
        and not settings.lookup_enrich_in_background
        and secondary_result
        and _result_has_gaps(result)
    ):
        _merge_gaps(result, secondary_result)

    existing = db.get(BarcodeCache, barcode)
    now = utcnow()
    if result:
        if existing:
            existing.source = result["source"]
            existing.title = result["title"]
            existing.brand = result["brand"]
            existing.quantity = result["quantity"]
            existing.product_type = result["product_type"]
            existing.found = True
            existing.lookup_attempted_at = now
        else:
            existing = BarcodeCache(
                barcode=barcode, source=result["source"], title=result["title"], brand=result["brand"],
                quantity=result["quantity"], product_type=result["product_type"], found=True,
                lookup_attempted_at=now, created_at=now,
            )
            db.add(existing)
    else:
        if existing:
            existing.source = "not_found"
            existing.found = False
            existing.lookup_attempted_at = now
        else:
            existing = BarcodeCache(
                barcode=barcode, source="not_found", found=False,
                lookup_attempted_at=now, created_at=now,
            )
            db.add(existing)
    db.commit()
    db.refresh(existing)
    return existing


def needs_background_enrich(cached: BarcodeCache) -> bool:
    if settings.lookup_strategy != "complement":
        return False
    if not settings.lookup_enrich_in_background:
        return False
    if not cached.found:
        return False
    _, secondary_fn = _get_lookup_functions()
    if secondary_fn is None:
        return False
    return not all([cached.brand, cached.quantity, cached.product_type])


def enrich_barcode_background(barcode: str) -> None:
    """Background task: call secondary API and fill gaps in cache."""
    from app.database import SessionLocal

    _, secondary_fn = _get_lookup_functions()
    if secondary_fn is None:
        return
    supplement = secondary_fn(barcode)
    if not supplement:
        logger.info("Background enrich %s: secondary returned nothing", barcode)
        return
    db = SessionLocal()
    try:
        cached = db.get(BarcodeCache, barcode)
        if not cached or not cached.found:
            return
        changed = False
        for field in ("brand", "quantity", "product_type"):
            if not getattr(cached, field) and supplement.get(field):
                setattr(cached, field, supplement[field])
                changed = True
        if changed:
            cached.source = f"{cached.source}+{supplement['source']}"
            db.commit()
            logger.info("Background enrich %s: filled gaps → %s", barcode, cached.source)
        else:
            logger.debug("Background enrich %s: no new data from secondary", barcode)
    finally:
        db.close()
