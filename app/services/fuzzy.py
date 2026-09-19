import json
import logging
import re

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.config import settings
from app.models import BarcodeMapping, Item

logger = logging.getLogger(__name__)

_QUANTITY_PATTERN = re.compile(
    r"\b\d+\s*(x\s*\d+\s*)?(g|kg|ml|l|cl|dl|oz|lb|lbs|fl\.?\s*oz|pack|pcs|ct|count)\b",
    re.IGNORECASE,
)
_EXTRA_SPACES = re.compile(r"\s{2,}")


def normalise_title(title: str, brand: str | None = None) -> str:
    result = title
    if brand:
        result = re.sub(re.escape(brand), "", result, flags=re.IGNORECASE)
    result = _QUANTITY_PATTERN.sub("", result)
    result = result.replace("-", " ").replace("_", " ")
    return _EXTRA_SPACES.sub(" ", result).strip()


def _score_pair(product: str, item_term: str) -> int:
    p = product.lower()
    f = item_term.lower()
    return max(
        fuzz.token_sort_ratio(p, f),
        fuzz.token_set_ratio(p, f),
        fuzz.partial_ratio(p, f),
    )


def fuzzy_match(
    title: str,
    brand: str | None,
    db: Session,
    threshold: int | None = None,
) -> list[dict]:
    if threshold is None:
        threshold = 0

    normalised = normalise_title(title, brand)
    if not normalised:
        return []

    items = db.query(Item).filter(Item.source == "mealie").all()
    candidates = []

    for item in items:
        score = _score_pair(normalised, item.name)
        aliases = []
        if item.aliases:
            try:
                aliases = json.loads(item.aliases)
            except (json.JSONDecodeError, TypeError):
                pass
        for alias in aliases:
            score = max(score, _score_pair(normalised, alias))

        candidates.append({
            "item_id": item.id,
            "item_name": item.name,
            "source": item.source,
            "score": int(score),
        })

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates


def try_auto_map(barcode: str, title: str, brand: str | None, db: Session) -> str | None:
    candidates = fuzzy_match(title, brand, db)
    if not candidates:
        return None

    top = candidates[0]
    if top["score"] < settings.fuzzy_match_threshold:
        return None

    if len(candidates) >= 2:
        second = candidates[1]
        gap = top["score"] - second["score"]
        if gap < settings.fuzzy_ambiguity_gap:
            logger.info(
                "Ambiguous match for %s: %s(%s) vs %s(%s), gap=%s < %s",
                barcode,
                top["item_name"],
                top["score"],
                second["item_name"],
                second["score"],
                gap,
                settings.fuzzy_ambiguity_gap,
            )
            return None

    existing = db.get(BarcodeMapping, barcode)
    if not existing:
        existing = BarcodeMapping(
            barcode=barcode,
            target_type="food",
            target_id=top["item_id"],
        )
        db.add(existing)

    existing.target_type = "food"
    existing.target_id = top["item_id"]
    existing.target_name = top["item_name"]
    existing.quantity = 1.0
    existing.unit_id = None
    existing.recipe_scale = 1.0
    existing.mapped_by = "auto"
    db.commit()

    logger.info("Auto-mapped %s -> %s (score=%s)", barcode, top["item_name"], top["score"])
    return top["item_id"]
