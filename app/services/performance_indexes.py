from __future__ import annotations

from sqlalchemy import text

from app.database import engine


def ensure_performance_indexes() -> None:
    """Create hot-path indexes for existing SQLite databases idempotently."""
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_retry_queue_next_retry_at "
            "ON retry_queue (next_retry_at, id)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_action_executions_action_created "
            "ON action_executions (action_id, created_at DESC)"
        ))
