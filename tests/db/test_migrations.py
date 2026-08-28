import sqlite3

import pytest

from mcp_kb_sqlite.db.migrations import MIGRATIONS, run_migrations


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    yield c
    c.close()


def test_creates_expected_tables(conn):
    run_migrations(conn)
    tables = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"entries", "entries_fts", "relations", "db_meta"} <= tables


def test_entries_columns(conn):
    run_migrations(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(entries)").fetchall()}
    assert cols == {
        "id", "ns", "key", "title", "description", "tags", "data",
        "created_at", "updated_at",
    }


def test_entries_ns_key_unique(conn):
    run_migrations(conn)
    conn.execute("INSERT INTO entries(ns, key, title) VALUES ('a', 'b', 'T1')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO entries(ns, key, title) VALUES ('a', 'b', 'T2')")


def test_schema_version_set_after_migrations(conn):
    run_migrations(conn)
    row = conn.execute(
        "SELECT value FROM db_meta WHERE key='schema_version'"
    ).fetchone()
    assert row["value"] == str(len(MIGRATIONS))


def test_run_migrations_twice_is_idempotent(conn):
    run_migrations(conn)
    run_migrations(conn)  # second pass must not re-run _migrate_v0 or raise
    row = conn.execute(
        "SELECT value FROM db_meta WHERE key='schema_version'"
    ).fetchone()
    assert row["value"] == str(len(MIGRATIONS))


def test_fts_index_follows_insert_update_delete(conn):
    run_migrations(conn)
    cur = conn.execute(
        "INSERT INTO entries(ns, key, title, description, tags) "
        "VALUES ('t', 'k', 'Alpha Title', 'a description', 'x') RETURNING id"
    )
    id_ = cur.fetchone()["id"]

    hit = conn.execute(
        "SELECT rowid FROM entries_fts WHERE entries_fts MATCH 'Alpha'"
    ).fetchone()
    assert hit["rowid"] == id_

    conn.execute("UPDATE entries SET title = 'Renamed' WHERE id = ?", (id_,))
    assert conn.execute(
        "SELECT rowid FROM entries_fts WHERE entries_fts MATCH 'Alpha'"
    ).fetchone() is None
    assert conn.execute(
        "SELECT rowid FROM entries_fts WHERE entries_fts MATCH 'Renamed'"
    ).fetchone()["rowid"] == id_

    conn.execute("DELETE FROM entries WHERE id = ?", (id_,))
    assert conn.execute(
        "SELECT rowid FROM entries_fts WHERE entries_fts MATCH 'Renamed'"
    ).fetchone() is None


def test_update_trigger_bumps_updated_at(conn):
    run_migrations(conn)
    cur = conn.execute(
        "INSERT INTO entries(ns, key, title) VALUES ('t', 'k', 'T') RETURNING id, updated_at"
    )
    row = cur.fetchone()
    id_ = row["id"]

    conn.execute(
        "UPDATE entries SET updated_at = '2000-01-01 00:00:00' WHERE id = ?", (id_,)
    )
    conn.execute("UPDATE entries SET title = 'T2' WHERE id = ?", (id_,))
    new_updated_at = conn.execute(
        "SELECT updated_at FROM entries WHERE id = ?", (id_,)
    ).fetchone()["updated_at"]
    assert new_updated_at != "2000-01-01 00:00:00"


def test_relations_cascade_delete(conn):
    run_migrations(conn)
    a = conn.execute(
        "INSERT INTO entries(ns, key, title) VALUES ('t', 'a', 'A') RETURNING id"
    ).fetchone()["id"]
    b = conn.execute(
        "INSERT INTO entries(ns, key, title) VALUES ('t', 'b', 'B') RETURNING id"
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO relations(from_id, to_id, rel) VALUES (?, ?, 'see_also')", (a, b)
    )

    conn.execute("DELETE FROM entries WHERE id = ?", (a,))

    remaining = conn.execute("SELECT * FROM relations").fetchall()
    assert remaining == []


def test_get_schema_version_bootstraps_at_zero_on_fresh_db(conn):
    from mcp_kb_sqlite.db.migrations import _get_schema_version

    assert _get_schema_version(conn) == 0
