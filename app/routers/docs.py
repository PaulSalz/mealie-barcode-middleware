import logging
from pathlib import Path

import re

import mistune
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.templating import templates

logger = logging.getLogger(__name__)
router = APIRouter()

DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs"

# Ordered list of docs with metadata for the index page.
DOCS_CATALOG = [
    {
        "slug": "middleware-setup",
        "title": "Middleware Setup",
        "description": "Deploy B2M, connect Mealie, configure lookup sources, Home Assistant and runtime settings.",
        "icon": "ti-server",
        "group": "Getting Started",
    },
    {
        "slug": "using-the-app",
        "title": "Using the App",
        "description": "Daily scanning, mappings, multi-target routing, Actions, labels and notifications.",
        "icon": "ti-player-play",
        "group": "Getting Started",
    },
    {
        "slug": "web-dashboard",
        "title": "Web Dashboard",
        "description": "Reference for Dashboard, Barcodes, Items, Actions, Labels, Activity and Settings.",
        "icon": "ti-browser",
        "group": "Getting Started",
    },
    {
        "slug": "barcode-workflow",
        "title": "How Barcode Scanning Works",
        "description": "End-to-end scan pipeline, lookup/cache behavior, targets, shopping routes and retries.",
        "icon": "ti-arrows-right-left",
        "group": "Scanning",
    },
    {
        "slug": "mobile-apps",
        "title": "Mobile App Scanning",
        "description": "Use BinaryEye, iOS Shortcuts or another HTTP scanner client with B2M tokens.",
        "icon": "ti-device-mobile",
        "group": "Scanning",
    },
    {
        "slug": "actions",
        "title": "Actions & Home Assistant",
        "description": "Create ACTION codes with the request builder and generated Home Assistant automations.",
        "icon": "ti-bolt",
        "group": "Automation & Labels",
    },
    {
        "slug": "label-printing",
        "title": "Labels & B21 Printing",
        "description": "Generate codes, design B21 labels, manage rolls, typography, calibration and print jobs.",
        "icon": "ti-printer",
        "group": "Automation & Labels",
    },
    {
        "slug": "esphome-firmware",
        "title": "ESPHome Firmware",
        "description": "Configure an ESPHome-based scanner client for B2M.",
        "icon": "ti-bolt",
        "group": "Scanner Hardware",
    },
    {
        "slug": "scanner-configuration",
        "title": "Scanner Configuration (GM67)",
        "description": "Program a GM67 module and verify the scanner data path.",
        "icon": "ti-qrcode",
        "group": "Scanner Hardware",
    },
    {
        "slug": "permissions",
        "title": "Users, Permissions & Administration",
        "description": "Per-user Appearance, printer access, Scan & Link control, database permissions and storage monitoring.",
        "icon": "ti-shield-lock",
        "group": "Administration",
    },
    {
        "slug": "troubleshooting",
        "title": "Troubleshooting",
        "description": "Diagnostics for scanning, Mealie, Actions, B21 printing, permissions and UI behavior.",
        "icon": "ti-lifebuoy",
        "group": "Reference",
    },
    {
        "slug": "gallery",
        "title": "Screenshots & Photos",
        "description": "Current screenshots and photos. UI screenshots can be replaced independently as the interface evolves.",
        "icon": "ti-photo",
        "group": "Reference",
    },
]

_DOCS_GROUP_ORDER = ["Getting Started", "Scanning", "Automation & Labels", "Scanner Hardware", "Administration", "Reference"]


def _build_docs_groups():
    groups = {g: [] for g in _DOCS_GROUP_ORDER}
    for doc in DOCS_CATALOG:
        groups[doc["group"]].append(doc)
    return [(g, groups[g]) for g in _DOCS_GROUP_ORDER if groups[g]]


_slug_to_meta = {d["slug"]: d for d in DOCS_CATALOG}

_md = mistune.create_markdown(escape=False, plugins=["table"])

_HEADING_RE = re.compile(r"<h(\d)(.*?)>(.*?)</h\1>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_DOC_LINK_RE = re.compile(r'href="([a-z0-9_-]+)\.md(#[^"]*)?"')


def _slugify(text: str) -> str:
    """Turn heading text into a URL-friendly anchor ID."""
    text = _TAG_RE.sub("", text)
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def _render_with_toc(raw: str) -> tuple[str, list[dict]]:
    """Render markdown and inject id attrs into h2 headings."""
    html = _md(raw)
    toc: list[dict] = []
    seen: dict[str, int] = {}

    def _replace_heading(m):
        level = int(m.group(1))
        attrs = m.group(2)
        inner = m.group(3)
        if level != 2:
            return m.group(0)
        slug = _slugify(inner)
        if slug in seen:
            seen[slug] += 1
            slug = f"{slug}-{seen[slug]}"
        else:
            seen[slug] = 0
        toc.append({"id": slug, "text": _TAG_RE.sub("", inner).strip()})
        return f'<h2 id="{slug}"{attrs}>{inner}</h2>'

    html = _HEADING_RE.sub(_replace_heading, html)
    html = _DOC_LINK_RE.sub(
        lambda m: f'href="/docs/{m.group(1)}{m.group(2) or ""}"', html
    )
    return html, toc


@router.get("/docs", response_class=HTMLResponse)
def docs_index(request: Request):
    return templates.TemplateResponse(request, "docs.html", {
        "doc_groups": _build_docs_groups(),
    })


@router.get("/docs/{slug}", response_class=HTMLResponse)
def docs_detail(request: Request, slug: str):
    meta = _slug_to_meta.get(slug)
    if not meta:
        return templates.TemplateResponse(request, "404.html", status_code=404)

    md_path = DOCS_DIR / f"{slug}.md"
    if not md_path.is_file():
        return templates.TemplateResponse(request, "404.html", status_code=404)

    raw = md_path.read_text(encoding="utf-8")
    lines = raw.split("\n", 1)
    if lines[0].startswith("# "):
        raw = lines[1] if len(lines) > 1 else ""

    html_content, toc = _render_with_toc(raw)

    return templates.TemplateResponse(request, "doc_detail.html", {
        "doc_title": meta["title"],
        "doc_icon": meta["icon"],
        "doc_slug": slug,
        "doc_html": html_content,
        "toc": toc,
    })
