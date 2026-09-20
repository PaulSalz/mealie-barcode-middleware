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
