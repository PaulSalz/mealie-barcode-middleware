from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    _migrate()
    Base.metadata.create_all(bind=engine)
    _backfill_barcode_targets()


def _add_column_if_missing(table: str, column: str, sql_type: str, columns: set[str]) -> None:
    if column in columns:
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
    columns.add(column)


def _migrate():
    """Small idempotent SQLite migrations without resetting user data."""
    insp = inspect(engine)
    tables = insp.get_table_names()

    if "api_tokens" in tables:
        columns = {c["name"] for c in insp.get_columns("api_tokens")}
        _add_column_if_missing("api_tokens", "token_prefix", "VARCHAR(8)", columns)
        _add_column_if_missing("api_tokens", "scanner_version", "VARCHAR", columns)
        _add_column_if_missing("api_tokens", "scanner_hostname", "VARCHAR", columns)
        _add_column_if_missing("api_tokens", "scanner_device", "VARCHAR", columns)
        _add_column_if_missing("api_tokens", "scanner_layout", "VARCHAR", columns)
        _add_column_if_missing("api_tokens", "scanner_last_seen_at", "DATETIME", columns)
        _add_column_if_missing("api_tokens", "scanner_uptime_seconds", "INTEGER", columns)
        _add_column_if_missing("api_tokens", "scanner_total_scans", "INTEGER", columns)
        _add_column_if_missing("api_tokens", "scanner_errors", "INTEGER", columns)
        _add_column_if_missing("api_tokens", "scanner_last_latency_ms", "INTEGER", columns)

    if "notifications" in tables and "activities" not in tables:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE notifications RENAME TO activities"))
        insp = inspect(engine)
        tables = insp.get_table_names()

    if "activities" in tables:
        columns = {c["name"] for c in insp.get_columns("activities")}
        if "is_dismissed" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE activities ADD COLUMN is_dismissed BOOLEAN DEFAULT 0"))
                conn.execute(text("UPDATE activities SET is_dismissed = 1 WHERE is_read = 1"))
            columns.add("is_dismissed")
        _add_column_if_missing("activities", "is_scan_event", "BOOLEAN DEFAULT 0", columns)
        _add_column_if_missing("activities", "target_type", "VARCHAR", columns)
        _add_column_if_missing("activities", "target_id", "VARCHAR", columns)
        _add_column_if_missing("activities", "target_name", "VARCHAR", columns)
        _add_column_if_missing("activities", "quantity_snapshot", "FLOAT", columns)
        _add_column_if_missing("activities", "unit_id_snapshot", "VARCHAR", columns)
        _add_column_if_missing("activities", "recipe_scale_snapshot", "FLOAT", columns)
        with engine.begin() as conn:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_activities_is_scan_event ON activities (is_scan_event)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_activities_target_id ON activities (target_id)"))

    if "barcode_cache" in tables:
        columns = {c["name"] for c in insp.get_columns("barcode_cache")}
        _add_column_if_missing("barcode_cache", "shopping_item_id", "VARCHAR", columns)
        _add_column_if_missing("barcode_cache", "custom_title", "VARCHAR", columns)
        _add_column_if_missing("barcode_cache", "custom_brand", "VARCHAR", columns)

    if "items" in tables:
        columns = {c["name"] for c in insp.get_columns("items")}
        _add_column_if_missing("items", "label_id", "VARCHAR", columns)
        _add_column_if_missing("items", "label_name", "VARCHAR", columns)
        _add_column_if_missing("items", "shopping_route", "VARCHAR DEFAULT 'default'", columns)
        _add_column_if_missing("items", "shopping_list_id", "VARCHAR", columns)
        with engine.begin() as conn:
            conn.execute(text("UPDATE items SET shopping_route = 'default' WHERE shopping_route IS NULL OR shopping_route = ''"))
        if "updated_at" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE items ADD COLUMN updated_at DATETIME"))
                conn.execute(text("UPDATE items SET updated_at = COALESCE(synced_at, created_at) WHERE updated_at IS NULL"))
            columns.add("updated_at")

    if "barcode_mappings" in tables:
        columns = {c["name"] for c in insp.get_columns("barcode_mappings")}
        if "target_id" not in columns:
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE barcode_mappings"))
        else:
            _add_column_if_missing("barcode_mappings", "shopping_list_id", "VARCHAR", columns)


def _backfill_barcode_targets() -> None:
    """Mirror legacy single mappings into the new multi-target table once."""
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    if not {"barcode_mappings", "barcode_targets"}.issubset(tables):
        return
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO barcode_targets (
                barcode, is_primary, enabled, target_type, target_id, target_name,
                quantity, unit_id, recipe_scale, destination_type,
                shopping_list_id, endpoint_url, mapped_by, created_at
            )
            SELECT
                m.barcode, 1, 1, m.target_type, m.target_id, m.target_name,
                CASE WHEN m.quantity <= 0.001 THEN NULL ELSE m.quantity END,
                m.unit_id, COALESCE(m.recipe_scale, 1.0), 'inherit',
                m.shopping_list_id, NULL, COALESCE(m.mapped_by, 'manual'), m.created_at
            FROM barcode_mappings AS m
            WHERE NOT EXISTS (
                SELECT 1 FROM barcode_targets AS t
                WHERE t.barcode = m.barcode AND t.is_primary = 1
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_barcode_targets_barcode ON barcode_targets (barcode)"))
        # BarcodeTarget intentionally has no hard FK because this DB predates the
        # table. A trigger gives existing SQLite files the expected cascade when the
        # user chooses Delete barcode.
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS trg_barcode_cache_delete_targets
            AFTER DELETE ON barcode_cache
            BEGIN
                DELETE FROM barcode_targets WHERE barcode = OLD.barcode;
            END
        """))
