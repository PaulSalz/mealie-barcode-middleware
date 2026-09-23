#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
import threading
from pathlib import Path

from sqlalchemy import inspect

# Import the delivery model before init_db so its table is part of Base.metadata.
from app import models  # noqa: F401
from app import models_scan_delivery  # noqa: F401
from app.database import engine, init_db
from app.events import EventBus
from app.services.bounded_executor import BoundedExecutor, ExecutorSaturated
from app.services.database_backup import create_verified_backup, remove_backup


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


async def _event_bus_case() -> None:
    bus = EventBus(max_queue_size=2)
    queue = bus.subscribe()
    bus._dispatch("one")
    bus._dispatch("two")
    bus._dispatch("three")
    assert queue.qsize() == 2, queue.qsize()
    assert await queue.get() == "two"
    assert await queue.get() == "three"
    bus.unsubscribe(queue)


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
    smoke_event_bus()
    smoke_bounded_executor()
    print("stability smoke ok")


if __name__ == "__main__":
    main()
