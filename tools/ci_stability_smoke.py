#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import sqlite3
import sys
import tempfile
import threading
import time
from datetime import timedelta
from pathlib import Path

# Allow direct execution via `python tools/ci_stability_smoke.py` from any cwd.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect

# Import models before init_db so their tables are part of Base.metadata.
from app import models  # noqa: F401, E402
from app import models_action_stats  # noqa: F401, E402
from app import models_scan_delivery  # noqa: F401, E402
from app import models_scan_stats  # noqa: F401, E402
from app.database import SessionLocal, engine, init_db  # noqa: E402
from app.events import EventBus  # noqa: E402
from app.models import ActionExecution, Activity  # noqa: E402
from app.models_action_stats import ActionAggregate  # noqa: E402
from app.models_scan_stats import ScanDailyStat  # noqa: E402
from app.routers import shopping_print as shopping_print_router  # noqa: E402
from app.services import mealie_extras  # noqa: E402
from app.services.action_stats import (  # noqa: E402
    action_stats,
    ensure_action_stats_backfilled,
    purge_action_executions,
)
from app.services.bounded_executor import BoundedExecutor, ExecutorSaturated  # noqa: E402
from app.services.database_backup import create_verified_backup, remove_backup  # noqa: E402
from app.services.performance_indexes import ensure_performance_indexes  # noqa: E402
from app.services.scan_stats import (  # noqa: E402
    ensure_scan_stats_backfilled,
    purge_raw_scan_history,
    target_scan_stats,
)
from app.utils import utcnow  # noqa: E402


def smoke_backup() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source_path = str(Path(tmp) / "source.db")
        writer = sqlite3.connect(source_path)
        try:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
            writer.execute("INSERT INTO sample(value) VALUES ('committed-in-wal')")
            writer.commit()

            backup_path = create_verified_backup(source_path)
            try:
                backup = sqlite3.connect(backup_path)
                try:
                    row = backup.execute("SELECT value FROM sample").fetchone()
                    assert row == ("committed-in-wal",), row
                    integrity = backup.execute("PRAGMA integrity_check").fetchone()
                    assert integrity == ("ok",), integrity
                finally:
                    backup.close()
            finally:
                remove_backup(backup_path)
        finally:
            writer.close()


def smoke_delivery_table() -> None:
    init_db()
    tables = set(inspect(engine).get_table_names())
    assert "scan_deliveries" in tables, sorted(tables)


def smoke_scan_aggregates() -> None:
    init_db()
    tables = set(inspect(engine).get_table_names())
    assert "scan_daily_stats" in tables, sorted(tables)

    db = SessionLocal()
    try:
        db.query(Activity).filter(Activity.barcode.like("ci-stat-barcode%" )).delete(synchronize_session=False)
        db.query(ScanDailyStat).filter(ScanDailyStat.target_id == "ci-stat-food").delete(synchronize_session=False)
        db.commit()

        for index in range(2):
            db.add(Activity(
                barcode=f"ci-stat-barcode-{index}",
                title="CI scan",
                message="CI Food",
                result="added",
                is_read=True,
                is_dismissed=True,
                is_scan_event=True,
                target_type="food",
                target_id="ci-stat-food",
                target_name="CI Food",
            ))
        db.add(Activity(
            barcode="ci-stat-barcode-old",
            title="Old CI scan",
            message="CI Food",
            result="added",
            is_read=True,
            is_dismissed=True,
            is_scan_event=True,
            target_type="food",
            target_id="ci-stat-food",
            target_name="CI Food",
            created_at=utcnow() - timedelta(days=400),
        ))
        db.commit()

        live_total = sum(
            row.count
            for row in db.query(ScanDailyStat).filter(ScanDailyStat.target_id == "ci-stat-food").all()
        )
        assert live_total == 3, live_total
    finally:
        db.close()

    ensure_scan_stats_backfilled()
    db = SessionLocal()
    try:
        stats = target_scan_stats(db, "food", "ci-stat-food")
        assert stats["total"] == 3, stats
        assert stats["days_7"] == 2, stats
        assert len(stats["recent"]) == 3, stats["recent"]

        deleted = purge_raw_scan_history(db, 365)
        assert deleted >= 1, deleted
        remaining_old = db.query(Activity).filter(Activity.barcode == "ci-stat-barcode-old").count()
        assert remaining_old == 0, remaining_old

        retained = target_scan_stats(db, "food", "ci-stat-food")
        assert retained["total"] == 3, retained
        assert retained["days_7"] == 2, retained
    finally:
        db.close()


def smoke_action_aggregates() -> None:
    init_db()
    tables = set(inspect(engine).get_table_names())
    assert "action_aggregates" in tables, sorted(tables)

    db = SessionLocal()
    try:
        db.query(ActionExecution).filter(ActionExecution.action_id == "ci-action").delete(synchronize_session=False)
        db.query(ActionAggregate).filter(ActionAggregate.action_id == "ci-action").delete(synchronize_session=False)
        db.commit()
        db.add(ActionExecution(
            action_id="ci-action", barcode="ACTION:ci-action", status="success",
            duration_ms=120, created_at=utcnow() - timedelta(days=200),
        ))
        db.add(ActionExecution(
            action_id="ci-action", barcode="ACTION:ci-action", status="failed",
            duration_ms=80, created_at=utcnow(),
        ))
        db.commit()
    finally:
        db.close()

    ensure_action_stats_backfilled()
    db = SessionLocal()
    try:
        stats = action_stats(db, "ci-action")
        assert stats["total"] == 2, stats
        assert stats["success"] == 1, stats
        assert stats["failed"] == 1, stats
        assert stats["avg_ms"] == 100.0, stats
        assert stats["last_status"] == "failed", stats

        deleted = purge_action_executions(db, 180)
        assert deleted >= 1, deleted
        retained = action_stats(db, "ci-action")
        assert retained["total"] == 2, retained
        assert retained["success"] == 1, retained
    finally:
        db.close()


def smoke_performance_indexes() -> None:
    ensure_performance_indexes()
    retry_indexes = {row["name"] for row in inspect(engine).get_indexes("retry_queue")}
    action_indexes = {row["name"] for row in inspect(engine).get_indexes("action_executions")}
    assert "ix_retry_queue_next_retry_at" in retry_indexes, retry_indexes
    assert "ix_action_executions_action_created" in action_indexes, action_indexes


def smoke_catalog_cache() -> None:
    mealie_extras.clear_catalog_cache()
    calls = 0
    calls_lock = threading.Lock()
    start = threading.Event()
    results: list[list[dict]] = []

    def loader():
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return [{"id": "ci-label", "name": "CI Label"}]

    def worker():
        start.wait()
        results.append(mealie_extras._cached("ci-catalog", loader))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    start.set()
    for thread in threads:
        thread.join(timeout=2)
        assert not thread.is_alive()

    assert calls == 1, calls
    assert len(results) == 8, len(results)
    assert all(rows == [{"id": "ci-label", "name": "CI Label"}] for rows in results)
    # Shopping Print must consume the cached catalog rather than the direct
    # Mealie get_labels() helper on every five-second list poll.
    assert shopping_print_router.cached_labels is mealie_extras.cached_labels


async def _event_bus_case() -> None:
    bus = EventBus(max_queue_size=2)
    event_queue = bus.subscribe()
    bus._dispatch("one")
    bus._dispatch("two")
    bus._dispatch("three")
    assert event_queue.qsize() == 2, event_queue.qsize()
    assert await event_queue.get() == "two"
    assert await event_queue.get() == "three"
    bus.unsubscribe(event_queue)


def smoke_event_bus() -> None:
    asyncio.run(_event_bus_case())


def smoke_bounded_executor() -> None:
    release = threading.Event()
    executor = BoundedExecutor(max_workers=1, max_pending=0, thread_name_prefix="ci-bound")
    first = executor.submit(release.wait)
    try:
        try:
            executor.submit(lambda: None)
        except ExecutorSaturated:
            pass
        else:
            raise AssertionError("bounded executor accepted work beyond capacity")
    finally:
        release.set()
        first.result(timeout=2)
        executor.shutdown()


def main() -> None:
    smoke_backup()
    smoke_delivery_table()
    smoke_scan_aggregates()
    smoke_action_aggregates()
    smoke_performance_indexes()
    smoke_catalog_cache()
    smoke_event_bus()
    smoke_bounded_executor()
    print("stability smoke ok")


if __name__ == "__main__":
    main()
