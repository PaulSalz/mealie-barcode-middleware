import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends
from fastapi.applications import FastAPI
from fastapi.staticfiles import StaticFiles

from app.admin_write_guard import AdminWriteGuardMiddleware
from app.barcode_dependencies import recover_known_barcode_cache
from app.config import settings
from app.database import init_db
from app.frontend_assets import ensure_frontend_assets
from app.middleware import CSRFOriginMiddleware, LoginRequiredMiddleware, RememberMeSessionMiddleware, SecurityHeadersMiddleware, get_session_secret
from app.permission_guard_v23 import PermissionGuardV23Middleware
from app.routers import access_v23, actions, appearance_v3, appearance_v24, barcodes, dashboard, database_backup, docs, health, integrations, items, label_printer, labels, localization, login, notifications, recipes, runtime_features, scan_gateway, scanner, settings as settings_router, shopping_print, target_editor_v6, theme_preview_v2, v30_fixes, version_api
from app.scan_timing_v6 import ScanTimingMiddleware
from app.services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
ensure_frontend_assets()


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
        logger.warning("UPCDB_ENABLED=True but UPCDB_API_KEY is not set — UPC Database will be skipped")
    sources = []
    if settings.off_enabled:
        sources.append("OpenFoodFacts")
    if upcdb_usable:
        sources.append("UPCDatabase")
    if sources:
        primary = "OpenFoodFacts" if settings.lookup_primary == "off" else "UPCDatabase"
        if primary not in sources:
            primary = sources[0]
        logger.info("Lookup: strategy=%s  primary=%s  sources=%s  background_enrich=%s", settings.lookup_strategy, primary, "+".join(sources), settings.lookup_enrich_in_background)
    else:
        logger.warning("No barcode lookup sources enabled — scans will always be 'not_found'")

    if not settings.middleware_base_url:
        logger.info("MIDDLEWARE_BASE_URL not set — notification action_url will use relative paths. Set MIDDLEWARE_BASE_URL=http://your-middleware-ip:9930 for full deep links in HA notifications.")
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Mealie Barcode Middleware", lifespan=lifespan, docs_url="/api/docs", redoc_url="/api/redoc")

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFOriginMiddleware)
app.add_middleware(AdminWriteGuardMiddleware)
app.add_middleware(PermissionGuardV23Middleware)
app.add_middleware(LoginRequiredMiddleware)
app.add_middleware(RememberMeSessionMiddleware, secret_key=get_session_secret(), max_age=settings.session_max_age_days * 24 * 3600)
app.add_middleware(ScanTimingMiddleware)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(version_api.router, tags=["system"])
app.include_router(dashboard.router, tags=["dashboard"])
app.include_router(docs.router, tags=["docs"])
# All public scan entry points live in one router. scan.py and scan_fast_v11.py
# are implementation modules and are deliberately not registered directly.
app.include_router(scan_gateway.router, tags=["scan"])
app.include_router(scanner.router, tags=["scanner"])
app.include_router(integrations.router, tags=["integrations"])
app.include_router(appearance_v3.router, tags=["ui"])
app.include_router(appearance_v24.router, tags=["ui"])
app.include_router(runtime_features.router, tags=["runtime"])
app.include_router(theme_preview_v2.router, tags=["theme"])
app.include_router(health.router, tags=["health"])
app.include_router(login.router, tags=["auth"])
app.include_router(localization.router, tags=["localization"])
app.include_router(
    barcodes.router,
    tags=["barcodes"],
    dependencies=[Depends(recover_known_barcode_cache)],
)
app.include_router(target_editor_v6.router, tags=["barcodes"])
app.include_router(items.router, tags=["items"])
app.include_router(recipes.router, tags=["recipes"])
app.include_router(labels.router, tags=["labels"])
app.include_router(label_printer.router, tags=["labels", "printer"])
app.include_router(shopping_print.router, tags=["shopping", "printer"])
app.include_router(v30_fixes.router, tags=["printer", "shopping"])
app.include_router(actions.router, tags=["actions"])
app.include_router(notifications.router, tags=["notifications"])
app.include_router(database_backup.router, tags=["database"])
app.include_router(access_v23.router, tags=["access", "theme", "database"])
app.include_router(settings_router.router, tags=["settings"])
