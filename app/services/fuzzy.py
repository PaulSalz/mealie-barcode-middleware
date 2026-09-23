import json
import logging
import re

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Item
from app.services.targets import add_target

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
    p = " ".join(product.casefold().split())
    f = " ".join(item_term.casefold().split())
    if p == f:
        return 100
    token_sort = fuzz.token_sort_ratio(p, f)
    token_set = fuzz.token_set_ratio(p, f)
    # partial_ratio is useful for longer product titles, but it over-ranks unrelated
    # items for very short searches such as "Tic". Damp it for short terms.
    partial = fuzz.partial_ratio(p, f)
    if min(len(p), len(f)) < 6:
        partial = int(partial * 0.72)
    score = max(token_sort, token_set, partial)
    if f.startswith(p) or p.startswith(f):
        score = max(score, 92)
    return int(score)


def fuzzy_match(title: str, brand: str | None, db: Session, threshold: int | None = None) -> list[dict]:
    if threshold is None:
        threshold = 0
    normalised = normalise_title(title, brand)
    if not normalised:
        return []

    items = db.query(Item).filter(Item.source == "mealie").all()
    candidates = []
    for item in items:
        score = _score_pair(normalised, item.name)
        exact = normalise_title(item.name).casefold() == normalised.casefold()
        aliases = []
        if item.aliases:
            try:
                aliases = json.loads(item.aliases)
            except (json.JSONDecodeError, TypeError):
                pass
        for alias in aliases:
            alias_text = str(alias)
            if normalise_title(alias_text).casefold() == normalised.casefold():
                exact = True
            score = max(score, _score_pair(normalised, alias_text))
        candidates.append({
            "item_id": item.id,
            "item_name": item.name,
            "source": item.source,
            "score": 100 if exact else int(score),
            "exact": exact,
            "default_unit_id": item.default_unit_id,
            "default_unit_name": item.default_unit_name,
        })

    candidates.sort(key=lambda c: (not c["exact"], -c["score"], c["item_name"].casefold()))
    return candidates


def try_auto_map(barcode: str, title: str, brand: str | None, db: Session) -> str | None:
    candidates = fuzzy_match(title, brand, db)
    if not candidates:
        return None

    top = candidates[0]
    if top["score"] < settings.fuzzy_match_threshold:
        return None

    # A real exact name/alias match wins even if another fuzzy candidate happens to
    # score close to it. This is important after deleting/re-scanning a barcode.
    if not top.get("exact") and len(candidates) >= 2:
        second = candidates[1]
        gap = top["score"] - second["score"]
        if gap < settings.fuzzy_ambiguity_gap:
            logger.info(
                "Ambiguous match for %s: %s(%s) vs %s(%s), gap=%s < %s",
                barcode, top["item_name"], top["score"], second["item_name"], second["score"],
                gap, settings.fuzzy_ambiguity_gap,
            )
            return None

    add_target(
        barcode,
        "food",
        top["item_id"],
        top["item_name"],
        db,
        quantity=1.0,
        unit_id=top.get("default_unit_id"),
        mapped_by="auto",
    )

    logger.info("Auto-mapped %s -> %s (score=%s exact=%s)", barcode, top["item_name"], top["score"], top.get("exact"))
    return top["item_id"]
