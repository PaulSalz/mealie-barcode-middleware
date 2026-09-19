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


def _migrate():
    """Small idempotent SQLite migrations.

    Barcode mappings changed from a Food-only foreign key to typed external
    Mealie targets. The old mapping table is intentionally discarded because
    there is no safe Recipe/Food inference for legacy rows. Other data remains
    untouched; a full /data volume reset is also supported for clean installs.
    """
    insp = inspect(engine)
    tables = insp.get_table_names()

    if "api_tokens" in tables:
        columns = {c["name"] for c in insp.get_columns("api_tokens")}
        if "token_prefix" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE api_tokens ADD COLUMN token_prefix VARCHAR(8)"))

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

    if "barcode_cache" in tables:
        columns = {c["name"] for c in insp.get_columns("barcode_cache")}
        if "shopping_item_id" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE barcode_cache ADD COLUMN shopping_item_id VARCHAR"))

    if "barcode_mappings" in tables:
        columns = {c["name"] for c in insp.get_columns("barcode_mappings")}
        if "target_id" not in columns:
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE barcode_mappings"))
