import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from mcp_kb_sqlite.db.migrations import needs_backup, run_migrations

_db_path: Path | None = None


def get_db_path() -> Path:
    global _db_path
    if _db_path is None:
        raw = os.environ.get("DB_PATH")
        if raw:
            _db_path = Path(raw)
        else:
            _db_path = Path.home() / ".ai-memory" / "kb.db"
        os.makedirs(_db_path.parent, exist_ok=True)
    return _db_path


@contextmanager
def get_conn():
    conn = sqlite3.connect(get_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _backup(conn: sqlite3.Connection) -> Path:
    """Snapshot the db file before an upgrade, via sqlite3's backup API so an
    in-progress WAL is captured consistently rather than copied mid-write."""
    path = get_db_path()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak_path = path.with_name(f"{path.name}.bak-{stamp}")
    bak_conn = sqlite3.connect(bak_path)
    try:
        conn.backup(bak_conn)
    finally:
        bak_conn.close()
    return bak_path


def init_db() -> None:
    with get_conn() as conn:
        if needs_backup(conn):
            _backup(conn)
        run_migrations(conn)
