from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.database import engine

logger = logging.getLogger(__name__)

Migration = tuple[str, Callable[[Connection], None]]


def _forward_barcode_targets(conn: Connection) -> None:
    """Materialize legacy primary mappings as additive targets once.

    BarcodeTarget is the canonical runtime representation. BarcodeMapping remains
    temporarily as a compatibility mirror for old routes/imports, but startup no
    longer recreates that mirror from targets in both directions.
    """
    tables = {row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
    if not {"barcode_mappings", "barcode_targets"}.issubset(tables):
        return
    conn.execute(text("""
        INSERT INTO barcode_targets (
            barcode, target_type, target_id, target_name, route,
            shopping_list_ids_json, quantity, unit_id, recipe_scale,
            position, enabled, mapped_by, created_at
        )
        SELECT
            m.barcode, m.target_type, m.target_id, m.target_name, 'inherit',
            CASE WHEN m.shopping_list_id IS NULL OR m.shopping_list_id = ''
                 THEN '[]' ELSE '[\"' || replace(m.shopping_list_id, '\"', '\\\"') || '\"]' END,
            CASE WHEN m.target_type = 'food' AND m.quantity <= 0.001 THEN NULL ELSE m.quantity END,
            m.unit_id, COALESCE(m.recipe_scale, 1.0), 0, 1,
            COALESCE(m.mapped_by, 'manual'), m.created_at
        FROM barcode_mappings m
        WHERE NOT EXISTS (
            SELECT 1 FROM barcode_targets t WHERE t.barcode = m.barcode
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_barcode_targets_barcode ON barcode_targets (barcode)"))


MIGRATIONS: tuple[Migration, ...] = (
    ("2026-09-23-001-forward-barcode-targets", _forward_barcode_targets),
)


def run_schema_migrations() -> list[str]:
    """Run ordered, transactional, once-only data migrations."""
    applied_now: list[str] = []
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                name VARCHAR PRIMARY KEY NOT NULL,
                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        applied = {
            row[0]
            for row in conn.execute(text("SELECT name FROM schema_migrations"))
        }
        for name, migration in MIGRATIONS:
            if name in applied:
                continue
            logger.info("Applying database migration %s", name)
            migration(conn)
            conn.execute(
                text("INSERT INTO schema_migrations (name) VALUES (:name)"),
                {"name": name},
            )
            applied_now.append(name)
    if applied_now:
        logger.info("Applied %d database migration(s): %s", len(applied_now), ", ".join(applied_now))
    return applied_now
