import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.mealie_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def delete_shopping_item(item_id: str) -> bool:
    """Delete one Mealie shopping-list line by id."""
    try:
        resp = httpx.delete(
            f"{settings.mealie_url}/api/households/shopping/items/{item_id}",
            headers=_headers(),
            timeout=5,
        )
        if resp.status_code in (200, 204, 404):
            return True
        logger.warning("Mealie shopping DELETE %s returned %s: %s", item_id, resp.status_code, resp.text)
    except httpx.HTTPError as exc:
        logger.warning("Mealie shopping DELETE %s failed: %s", item_id, exc)
    return False
