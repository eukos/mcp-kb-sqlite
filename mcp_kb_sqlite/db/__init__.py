import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from mcp_kb_sqlite.db.migrations import run_migrations

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


def init_db() -> None:
    with get_conn() as conn:
        run_migrations(conn)
