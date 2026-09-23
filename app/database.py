from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False, "timeout": 30},
    echo=False,
)


@event.listens_for(engine, "connect")
def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
    """Apply cheap per-connection pragmas only."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _configure_sqlite_database() -> None:
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")


def init_db():
    """Bring old schemas forward, create current tables, then run tracked data migrations."""
    _configure_sqlite_database()
    # Historical releases performed additive column migrations without a version
    # table. Keep this idempotent compatibility pass until all supported installs
    # have crossed the boundary, but put every new data migration in the tracked
    # registry below rather than adding more startup backfill code here.
    _migrate_legacy_schema()
    Base.metadata.create_all(bind=engine)
    from app.services.schema_migrations import run_schema_migrations
    run_schema_migrations()


def _add_column_if_missing(table: str, column: str, sql_type: str, columns: set[str]) -> None:
    if column in columns:
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
    columns.add(column)


def _migrate_legacy_schema():
    """Compatibility pass for pre-versioned additive SQLite schema changes.

    Do not add new data migrations here. New changes belong in
    app.services.schema_migrations where they are recorded exactly once.
    """
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
        _add_column_if_missing("activities", "targets_json", "TEXT", columns)
        _add_column_if_missing("activities", "quantity_snapshot", "FLOAT", columns)
        _add_column_if_missing("activities", "unit_id_snapshot", "VARCHAR", columns)
        _add_column_if_missing("activities", "recipe_scale_snapshot", "FLOAT", columns)
        with engine.begin() as conn:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_activities_is_scan_event ON activities (is_scan_event)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_activities_target_id ON activities (target_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_activities_scan_created ON activities (is_scan_event, created_at DESC)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_activities_barcode_scan_created ON activities (barcode, is_scan_event, created_at DESC)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_activities_barcode_read ON activities (barcode, is_read)"))

    if "barcode_cache" in tables:
        columns = {c["name"] for c in insp.get_columns("barcode_cache")}
        _add_column_if_missing("barcode_cache", "shopping_item_id", "VARCHAR", columns)
        _add_column_if_missing("barcode_cache", "custom_title", "VARCHAR", columns)
        _add_column_if_missing("barcode_cache", "custom_brand", "VARCHAR", columns)
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE barcode_cache
                SET found = 1
                WHERE found = 0
                  AND custom_title IS NOT NULL
                  AND trim(custom_title) <> ''
            """))

    if "items" in tables:
        columns = {c["name"] for c in insp.get_columns("items")}
        _add_column_if_missing("items", "label_id", "VARCHAR", columns)
        _add_column_if_missing("items", "label_name", "VARCHAR", columns)
        _add_column_if_missing("items", "default_unit_id", "VARCHAR", columns)
        _add_column_if_missing("items", "default_unit_name", "VARCHAR", columns)
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
