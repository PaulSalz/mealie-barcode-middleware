from __future__ import annotations

from app.services import niimblue


def print_images_base64(
    pages: list[dict],
    *,
    width_mm: float,
    height_mm: float,
    density: int | None = None,
    label_type: int | None = None,
    dpi: int | None = None,
    threshold: int = 128,
    print_direction: str | None = None,
    print_task: str | None = None,
) -> dict:
    """Submit a whole B21 queue as one native niimblue-node multi-page job.

    niimblue-node supports a ``pages`` array. Keeping the complete queue in one
    printer job avoids reconnect/busy races between consecutive HTTP print jobs.
    """
    cfg = niimblue.config()
    if width_mm <= 0 or height_mm <= 0:
        raise ValueError("Label dimensions must be positive")
    if width_mm > cfg["max_label_width_mm"] + 0.01:
        raise ValueError(
            f"Label is {width_mm:g} mm wide, but the configured printer limit is "
            f"{cfg['max_label_width_mm']:g} mm"
        )
    if not isinstance(pages, list) or not pages:
        raise ValueError("At least one label page is required")
    if len(pages) > 100:
        raise ValueError("At most 100 label pages can be printed in one queue")

    clean_pages: list[dict] = []
    total_quantity = 0
    for page in pages:
        if not isinstance(page, dict):
            raise ValueError("Invalid label page")
        image_base64 = str(page.get("image_base64") or page.get("imageBase64") or "")
        if image_base64.startswith("data:") and "," in image_base64:
            image_base64 = image_base64.split(",", 1)[1]
        if not image_base64:
            raise ValueError("Every label page requires a rendered image")
        if len(image_base64) > 12_000_000:
            raise ValueError("Rendered label page is too large")
        quantity = max(1, min(int(page.get("quantity") or 1), 99))
        total_quantity += quantity
        clean_pages.append({"imageBase64": image_base64, "quantity": quantity})

    resolved_dpi = max(100, min(int(dpi or cfg["dpi"]), 1200))
    resolved_density = max(1, min(int(density or cfg["density"]), 5))
    requested_label_type = max(1, int(label_type or cfg["label_type"]))
    resolved_threshold = max(1, min(int(threshold or 128), 255))
    px_per_mm = resolved_dpi / 25.4

    with niimblue._print_lock:
        niimblue._require_connected()
        media = niimblue.detected_media()
        media_label_type = media.get("label_type") if media.get("tag_present") else None
        resolved_label_type = int(media_label_type or requested_label_type)
        payload = {
            "printDirection": print_direction or cfg["print_direction"],
            "printTask": print_task or cfg["print_task"],
            "quantity": 1,
            "labelType": resolved_label_type,
            "density": resolved_density,
            "pages": clean_pages,
            "labelWidth": max(8, round(width_mm * px_per_mm)),
            "labelHeight": max(8, round(height_mm * px_per_mm)),
            "imageFit": "contain",
            "imagePosition": "centre",
            "threshold": resolved_threshold,
        }
        # A multi-page job legitimately takes longer than one label. Scale the
        # HTTP wait window with the requested quantity but keep an upper bound.
        timeout = max(float(cfg["timeout"]), min(300.0, 20.0 + total_quantity * 20.0))
        try:
            response = niimblue._request("POST", "/print", json=payload, timeout=timeout)
        except Exception as exc:
            raise RuntimeError(niimblue._http_error_message(exc, action="queue print")) from exc

    try:
        data = response.json()
    except ValueError:
        data = {"message": response.text or "Printed"}
    return {
        "ok": True,
        "response": data,
        "pages": len(clean_pages),
        "quantity": total_quantity,
        "pixels": [payload["labelWidth"], payload["labelHeight"]],
        "density": resolved_density,
        "label_type": resolved_label_type,
        "label_type_source": "rfid" if media.get("tag_present") and media.get("label_type") else "requested",
        "media": media,
    }
