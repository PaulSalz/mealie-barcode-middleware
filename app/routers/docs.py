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

DOCS_CATALOG = [
    {
        "slug": "middleware-setup",
        "title": "Middleware Setup",
        "description": "Deploy B2M, connect Mealie, configure persistent data, scanners and optional integrations.",
        "icon": "ti-server",
        "group": "Getting Started",
    },
    {
        "slug": "using-the-app",
        "title": "Using the App",
        "description": "Daily workflows: scanning, linking targets, items, recipes, actions and labels.",
        "icon": "ti-player-play",
        "group": "Getting Started",
    },
    {
        "slug": "web-dashboard",
        "title": "Web Dashboard",
        "description": "Current dashboard, tables, live feedback, settings, appearance and administration UI.",
        "icon": "ti-browser",
        "group": "Getting Started",
    },
    {
        "slug": "barcode-workflow",
        "title": "Barcode & Routing Workflow",
        "description": "How a scan is resolved and routed to one or several food, recipe or action targets.",
        "icon": "ti-arrows-right-left",
        "group": "Scanning & Automation",
    },
    {
        "slug": "actions",
        "title": "Actions & Home Assistant",
        "description": "Build reusable webhook Actions, parameters and Home Assistant automations without hand-writing JSON.",
        "icon": "ti-bolt",
        "group": "Scanning & Automation",
    },
    {
        "slug": "mobile-apps",
        "title": "Mobile App Scanning",
        "description": "Use BinaryEye, iOS Shortcuts or another Bearer-token client as a scanner.",
        "icon": "ti-device-mobile",
        "group": "Scanning & Automation",
    },
    {
        "slug": "b21-printing",
        "title": "Labels & B21 Pro Printing",
        "description": "Generate codes, design physical B21 labels, manage rolls, calibration and print jobs.",
        "icon": "ti-printer",
        "group": "Labels & Printing",
    },
    {
        "slug": "permissions-appearance",
        "title": "Users, Permissions & Appearance",
        "description": "Granular write permissions, personal themes, rainbow mode and database access boundaries.",
        "icon": "ti-shield-lock",
        "group": "Administration",
    },
    {
        "slug": "esphome-firmware",
        "title": "ESPHome Scanner Firmware",
        "description": "Configure an ESPHome-based scanner client and authenticate it against B2M.",
        "icon": "ti-bolt",
        "group": "Scanner Reference",
    },
    {
        "slug": "scanner-configuration",
        "title": "Scanner Configuration",
        "description": "Scanner-side configuration, tokens, keyboard layout and diagnostics.",
        "icon": "ti-scan",
        "group": "Scanner Reference",
    },
    {
        "slug": "troubleshooting",
        "title": "Troubleshooting",
        "description": "Diagnostics for scans, Mealie routing, actions, B21 printing, permissions and UI issues.",
        "icon": "ti-lifebuoy",
        "group": "Reference",
    },
    {
        "slug": "gallery",
        "title": "Screenshots",
        "description": "UI screenshots and annotated workflow examples. Additional screenshots can be added without changing the guides.",
        "icon": "ti-photo",
        "group": "Reference",
    },
]

_DOCS_GROUP_ORDER = ["Getting Started", "Scanning & Automation", "Labels & Printing", "Administration", "Scanner Reference", "Reference"]


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
    text = _TAG_RE.sub("", text)
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def _render_with_toc(raw: str) -> tuple[str, list[dict]]:
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
    return templates.TemplateResponse(request, "docs.html", {"doc_groups": _build_docs_groups()})


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
