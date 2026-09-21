import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi.applications import FastAPI
from fastapi.staticfiles import StaticFiles

from app.admin_write_guard import AdminWriteGuardMiddleware
from app.config import settings
from app.database import init_db
from app.middleware import CSRFOriginMiddleware, LoginRequiredMiddleware, RememberMeSessionMiddleware, SecurityHeadersMiddleware, get_session_secret
from app.routers import actions, appearance_v3, barcodes, dashboard, docs, health, integrations, items, label_printer, labels, login, notifications, recipes, runtime_features, scan, scan_fast_v11, scanner, settings as settings_router, target_editor_v6, theme_preview_v2, version_api
from app.scan_timing_v6 import ScanTimingMiddleware
from app.services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database initialized")

    settings.load_overrides_from_db()

    from app.database import SessionLocal
    from app.theme import get_theme
    from app.templating import set_cached_theme
    db = SessionLocal()
    try:
        set_cached_theme(get_theme(db))
    finally:
        db.close()

    upcdb_usable = settings.upcdb_enabled and bool(settings.upcdb_api_key)
    if settings.upcdb_enabled and not settings.upcdb_api_key:
        logger.warning(
            "UPCDB_ENABLED=True but UPCDB_API_KEY is not set — UPC Database will be skipped"
        )
    sources = []
    if settings.off_enabled:
        sources.append("OpenFoodFacts")
    if upcdb_usable:
        sources.append("UPCDatabase")
    if sources:
        primary = "OpenFoodFacts" if settings.lookup_primary == "off" else "UPCDatabase"
        if primary not in sources:
            primary = sources[0]
        logger.info(
            "Lookup: strategy=%s  primary=%s  sources=%s  background_enrich=%s",
            settings.lookup_strategy,
            primary,
            "+".join(sources),
            settings.lookup_enrich_in_background,
        )
    else:
        logger.warning("No barcode lookup sources enabled — scans will always be 'not_found'")

    if not settings.middleware_base_url:
        logger.info(
            "MIDDLEWARE_BASE_URL not set — notification action_url will use relative paths. "
            "Set MIDDLEWARE_BASE_URL=http://your-middleware-ip:9930 for full deep links in HA notifications."
        )
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Mealie Barcode Middleware", lifespan=lifespan, docs_url="/api/docs", redoc_url="/api/redoc")

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFOriginMiddleware)
app.add_middleware(AdminWriteGuardMiddleware)
app.add_middleware(LoginRequiredMiddleware)
app.add_middleware(RememberMeSessionMiddleware, secret_key=get_session_secret(), max_age=settings.session_max_age_days * 24 * 3600)
app.add_middleware(ScanTimingMiddleware)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Keep version first so all clients use the same release source of truth.
app.include_router(version_api.router, tags=["system"])
app.include_router(dashboard.router, tags=["dashboard"])
app.include_router(docs.router, tags=["docs"])
# Fast local acknowledgement for mapped scans must precede the legacy /scan route.
app.include_router(scan_fast_v11.router, tags=["scan"])
app.include_router(scan.router, tags=["scan"])
app.include_router(scanner.router, tags=["scanner"])
# Existing integration routes keep priority for authenticated theme/item actions.
app.include_router(integrations.router, tags=["integrations"])
app.include_router(appearance_v3.router, tags=["ui"])
app.include_router(runtime_features.router, tags=["runtime"])
app.include_router(theme_preview_v2.router, tags=["theme"])
app.include_router(health.router, tags=["health"])
app.include_router(login.router, tags=["auth"])
app.include_router(barcodes.router, tags=["barcodes"])
app.include_router(target_editor_v6.router, tags=["barcodes"])
app.include_router(items.router, tags=["items"])
app.include_router(recipes.router, tags=["recipes"])
app.include_router(labels.router, tags=["labels"])
app.include_router(label_printer.router, tags=["labels", "printer"])
app.include_router(actions.router, tags=["actions"])
app.include_router(notifications.router, tags=["notifications"])
app.include_router(settings_router.router, tags=["settings"])
