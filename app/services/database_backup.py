from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path


def create_verified_backup(db_path: str) -> str:
    """Create a consistent online SQLite snapshot and verify it before download.

    Copying only the main database file is not safe while WAL mode is active,
    because recent committed pages may still live in the -wal file. SQLite's
    backup API takes a transactionally consistent snapshot while the application
    remains online.
    """
    source_path = str(Path(db_path).expanduser().resolve())
    if not os.path.isfile(source_path):
        raise FileNotFoundError(source_path)

    fd, backup_path = tempfile.mkstemp(prefix="b2m-backup-", suffix=".db")
    os.close(fd)

    source = None
    destination = None
    try:
        source = sqlite3.connect(source_path, timeout=30.0)
        destination = sqlite3.connect(backup_path, timeout=30.0)
        source.execute("PRAGMA busy_timeout=30000")
        destination.execute("PRAGMA busy_timeout=30000")

        source.backup(destination, pages=256, sleep=0.05)
        destination.commit()

        result = destination.execute("PRAGMA integrity_check").fetchone()
        if not result or str(result[0]).strip().lower() != "ok":
            detail = result[0] if result else "no result"
            raise RuntimeError(f"SQLite backup integrity check failed: {detail}")

        return backup_path
    except Exception:
        try:
            os.unlink(backup_path)
        except OSError:
            pass
        raise
    finally:
        if destination is not None:
            destination.close()
        if source is not None:
            source.close()


def remove_backup(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
