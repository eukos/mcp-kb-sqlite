def _migrate_v0(conn) -> None:
    """Baseline schema — single entries table with FTS on title/description/tags."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS db_meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS entries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ns          TEXT NOT NULL,
            key         TEXT NOT NULL,
            title       TEXT NOT NULL,
            description TEXT,
            tags        TEXT,
            data        TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ns, key)
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts
            USING fts5(title, description, tags, content='entries', content_rowid='id');

        CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
            INSERT INTO entries_fts(rowid, title, description, tags)
            VALUES (new.id, new.title, new.description, new.tags);
        END;

        CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
            INSERT INTO entries_fts(entries_fts, rowid, title, description, tags)
            VALUES ('delete', old.id, old.title, old.description, old.tags);
        END;

        CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
            INSERT INTO entries_fts(entries_fts, rowid, title, description, tags)
            VALUES ('delete', old.id, old.title, old.description, old.tags);
            INSERT INTO entries_fts(rowid, title, description, tags)
            VALUES (new.id, new.title, new.description, new.tags);
            UPDATE entries SET updated_at = CURRENT_TIMESTAMP WHERE id = new.id;
        END;

        CREATE TABLE IF NOT EXISTS relations (
            from_id  INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
            to_id    INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
            rel      TEXT NOT NULL,
            PRIMARY KEY (from_id, to_id, rel)
        );
    """)


def _migrate_v1(conn) -> None:
    """Add `data` to the FTS index — entry payloads become searchable, not just
    title/description/tags. FTS5 columns can't be altered in place, so the virtual
    table is dropped and recreated, then backfilled via the 'rebuild' command."""
    conn.executescript("""
        DROP TRIGGER IF EXISTS entries_ai;
        DROP TRIGGER IF EXISTS entries_ad;
        DROP TRIGGER IF EXISTS entries_au;
        DROP TABLE IF EXISTS entries_fts;

        CREATE VIRTUAL TABLE entries_fts
            USING fts5(title, description, tags, data, content='entries', content_rowid='id');

        INSERT INTO entries_fts(entries_fts) VALUES ('rebuild');

        CREATE TRIGGER entries_ai AFTER INSERT ON entries BEGIN
            INSERT INTO entries_fts(rowid, title, description, tags, data)
            VALUES (new.id, new.title, new.description, new.tags, new.data);
        END;

        CREATE TRIGGER entries_ad AFTER DELETE ON entries BEGIN
            INSERT INTO entries_fts(entries_fts, rowid, title, description, tags, data)
            VALUES ('delete', old.id, old.title, old.description, old.tags, old.data);
        END;

        CREATE TRIGGER entries_au AFTER UPDATE ON entries BEGIN
            INSERT INTO entries_fts(entries_fts, rowid, title, description, tags, data)
            VALUES ('delete', old.id, old.title, old.description, old.tags, old.data);
            INSERT INTO entries_fts(rowid, title, description, tags, data)
            VALUES (new.id, new.title, new.description, new.tags, new.data);
            UPDATE entries SET updated_at = CURRENT_TIMESTAMP WHERE id = new.id;
        END;
    """)


MIGRATIONS = [_migrate_v0, _migrate_v1]


def _get_schema_version(conn) -> int:
    import sqlite3
    try:
        row = conn.execute("SELECT value FROM db_meta WHERE key='schema_version'").fetchone()
        return int(row["value"]) if row else 0
    except sqlite3.OperationalError:
        return 0


def _set_schema_version(conn, version: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO db_meta(key, value) VALUES ('schema_version', ?)",
        (str(version),),
    )


def needs_backup(conn) -> bool:
    """True only when an existing (already-versioned) db has pending migrations —
    never for a fresh install, which has nothing worth backing up yet."""
    version = _get_schema_version(conn)
    return 0 < version < len(MIGRATIONS)


def run_migrations(conn) -> None:
    version = _get_schema_version(conn)
    for i, fn in enumerate(MIGRATIONS, start=1):
        if i > version:
            fn(conn)
            _set_schema_version(conn, i)
