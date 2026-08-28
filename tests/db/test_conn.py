from pathlib import Path

import pytest

import mcp_kb_sqlite.db as db_module
from mcp_kb_sqlite.db import get_conn, get_db_path, init_db


@pytest.fixture(autouse=True)
def _reset_db_path_cache():
    """get_db_path() caches its result in a module-level global — clear it so each
    test starts fresh regardless of what a previous test resolved."""
    db_module._db_path = None
    yield
    db_module._db_path = None


def test_default_path_when_db_path_unset(monkeypatch):
    monkeypatch.delenv("DB_PATH", raising=False)
    assert get_db_path() == Path.home() / ".ai-memory" / "kb.db"


def test_db_path_env_override(monkeypatch, tmp_path):
    target = tmp_path / "custom" / "kb.db"
    monkeypatch.setenv("DB_PATH", str(target))
    assert get_db_path() == target


def test_db_path_result_is_cached(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "first.db"))
    first = get_db_path()
    monkeypatch.setenv("DB_PATH", str(tmp_path / "second.db"))
    assert get_db_path() == first


def test_db_path_creates_parent_dir(monkeypatch, tmp_path):
    target = tmp_path / "nested" / "dir" / "kb.db"
    monkeypatch.setenv("DB_PATH", str(target))
    get_db_path()
    assert target.parent.is_dir()


def test_get_conn_sets_pragmas(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "kb.db"))
    with get_conn() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_get_conn_commits_on_clean_exit(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "kb.db"))
    init_db()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO entries(ns, key, title) VALUES ('t', 'k', 'Title')"
        )
    with get_conn() as conn:
        row = conn.execute("SELECT title FROM entries WHERE ns='t' AND key='k'").fetchone()
    assert row["title"] == "Title"


def test_get_conn_does_not_commit_on_exception(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "kb.db"))
    init_db()
    with pytest.raises(ValueError), get_conn() as conn:
        conn.execute(
            "INSERT INTO entries(ns, key, title) VALUES ('t', 'k', 'Title')"
        )
        raise ValueError("boom")
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM entries WHERE ns='t' AND key='k'").fetchone()
    assert row is None


def test_init_db_creates_schema(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "kb.db"))
    init_db()
    with get_conn() as conn:
        tables = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {"entries", "relations", "db_meta"} <= tables


def test_init_db_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "kb.db"))
    init_db()
    init_db()  # must not raise or duplicate anything
    with get_conn() as conn:
        version = conn.execute(
            "SELECT value FROM db_meta WHERE key='schema_version'"
        ).fetchone()["value"]
    assert version == "1"
