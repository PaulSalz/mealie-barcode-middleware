#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path

# Allow direct execution via `python tools/ci_stability_smoke.py` from any cwd.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect

# Import models before init_db so their tables are part of Base.metadata.
from app import models  # noqa: F401, E402
from app import models_scan_delivery  # noqa: F401, E402
from app import models_scan_stats  # noqa: F401, E402
from app.database import SessionLocal, engine, init_db  # noqa: E402
from app.events import EventBus  # noqa: E402
from app.models import Activity  # noqa: E402
from app.models_scan_stats import ScanDailyStat  # noqa: E402
from app.services.bounded_executor import BoundedExecutor, ExecutorSaturated  # noqa: E402
from app.services.database_backup import create_verified_backup, remove_backup  # noqa: E402
from app.services.scan_stats import ensure_scan_stats_backfilled  # noqa: E402


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
        db.query(Activity).filter(Activity.barcode == "ci-stat-barcode").delete()
        db.query(ScanDailyStat).filter(ScanDailyStat.target_id == "ci-stat-food").delete()
        db.commit()

        for _ in range(2):
            db.add(Activity(
                barcode="ci-stat-barcode",
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
            db.commit()

        live = db.query(ScanDailyStat).filter(ScanDailyStat.target_id == "ci-stat-food").one()
        assert live.count == 2, live.count
    finally:
        db.close()

    # Rebuilding from raw history must be idempotent and preserve the same count.
    ensure_scan_stats_backfilled()
    db = SessionLocal()
    try:
        rebuilt = db.query(ScanDailyStat).filter(ScanDailyStat.target_id == "ci-stat-food").one()
        assert rebuilt.count == 2, rebuilt.count
    finally:
        db.close()


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
    smoke_event_bus()
    smoke_bounded_executor()
    print("stability smoke ok")


if __name__ == "__main__":
    main()
