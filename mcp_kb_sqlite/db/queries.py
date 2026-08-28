import json
import sqlite3

from mcp_kb_sqlite.db import get_conn


class EntryNotFound(Exception):
    def __init__(self, id: int):
        self.id = id
        super().__init__(f"id={id}")


class EntryClash(Exception):
    def __init__(self, ns: str, key: str, id: int):
        self.ns = ns
        self.key = key
        self.id = id
        super().__init__(f"{ns}/{key} already exists (id={id})")


def _ns_params(ns: str) -> list:
    return [ns, ns + "/%"]


def _ns_filter_sql(ns: str | None) -> tuple[str, list]:
    """SQL condition (without leading AND/WHERE) plus its params for an ns-prefix filter.
    Empty string/params when ns is None — callers splice it into their own WHERE clause."""
    if not ns:
        return "", []
    return "(e.ns = ? OR e.ns LIKE ?)", _ns_params(ns)


def _clash(conn, ns: str, key: str):
    return conn.execute(
        "SELECT id FROM entries WHERE ns = ? AND key = ?", (ns, key)
    ).fetchone()


def create_entry(ns, key, title, description, tags, data) -> dict:
    """Insert a new entry. Raises ValueError if ns/key/title missing, EntryClash if the
    (ns, key) pair is taken. Returns {'id', 'ns', 'key'}."""
    if not ns or not key or not title:
        raise ValueError("create requires ns, key, and title (or pass id to update)")
    with get_conn() as conn:
        clash = _clash(conn, ns, key)
        if clash:
            raise EntryClash(ns, key, clash["id"])
        cur = conn.execute(
            """
            INSERT INTO entries(ns, key, title, description, tags, data)
            VALUES (?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (ns, key, title, description, json.dumps(tags) if tags else None, data),
        )
        id_ = cur.fetchone()["id"]
    return {"id": id_, "ns": ns, "key": key}


def _update_sets(ns, key, title, description, tags, data) -> tuple[list[str], list]:
    """Column assignments for the fields that were actually passed.

    A field left as None is omitted entirely; "" (or [] for tags) clears it.
    Column names come from these literals only — never from caller input.
    """
    sets: list[str] = []
    params: list = []
    for col, provided, val in (
        ("ns", ns is not None, ns),
        ("key", key is not None, key),
        ("title", title is not None, title),
        ("description", description is not None, description or None),
        ("tags", tags is not None, json.dumps(tags) if tags else None),
        ("data", data is not None, data or None),
    ):
        if provided:
            sets.append(f"{col} = ?")
            params.append(val)
    return sets, params


def update_entry(id, ns, key, title, description, tags, data) -> dict:
    """Patch-update an entry. Raises ValueError for invalid input, EntryNotFound if id
    doesn't exist, EntryClash if renaming (ns, key) collides with another entry.
    Returns {'id', 'ns', 'key', 'changed': [col, ...]}."""
    if "" in (ns, key, title):
        raise ValueError("ns, key, and title cannot be cleared")
    sets, params = _update_sets(ns, key, title, description, tags, data)
    if not sets:
        raise ValueError("nothing to update — pass at least one field alongside id")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, ns, key FROM entries WHERE id = ?", (id,)
        ).fetchone()
        if not row:
            raise EntryNotFound(id)
        new_ns = ns if ns is not None else row["ns"]
        new_key = key if key is not None else row["key"]
        if (new_ns, new_key) != (row["ns"], row["key"]):
            clash = _clash(conn, new_ns, new_key)
            if clash:
                raise EntryClash(new_ns, new_key, clash["id"])
        # SET clause interpolates only the literal column names from _update_sets(); every
        # caller-supplied value is bound as a parameter. updated_at is set by the
        # entries_au trigger, not here.
        sql = f"UPDATE entries SET {', '.join(sets)} WHERE id = ?"
        conn.execute(sql, [*params, id])
    changed = [s.split(" = ")[0] for s in sets]
    return {"id": id, "ns": new_ns, "key": new_key, "changed": changed}


def get_entry(id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, ns, key, title, description, tags, data, created_at, updated_at "
            "FROM entries WHERE id = ?",
            (id,),
        ).fetchone()


def search_entries(query: str, ns: str | None, limit: int, offset: int) -> list[sqlite3.Row]:
    ns_sql, ns_params = _ns_filter_sql(ns)
    with get_conn() as conn:
        # ns_sql is a fixed literal from _ns_filter_sql(), never caller input; the ns
        # value itself is bound as a parameter via ns_params.
        return conn.execute(
            f"""
            SELECT e.id, e.ns, e.key, e.title, e.updated_at,
                   snippet(entries_fts, 1, '**', '**', '...', 20) AS snip
            FROM entries_fts
            JOIN entries e ON e.id = entries_fts.rowid
            WHERE entries_fts MATCH ?
              {"AND " + ns_sql if ns_sql else ""}
            ORDER BY bm25(entries_fts) ASC
            LIMIT ? OFFSET ?
            """,
            [query, *ns_params, limit, offset],
        ).fetchall()


def list_entries(ns: str | None, limit: int, offset: int) -> tuple[list[sqlite3.Row], int]:
    ns_sql, ns_params = _ns_filter_sql(ns)
    where = f"WHERE {ns_sql}" if ns_sql else ""
    with get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM entries e {where}", ns_params
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT e.id, e.ns, e.key, e.title, e.updated_at
            FROM entries e
            {where}
            ORDER BY e.updated_at DESC
            LIMIT ? OFFSET ?
            """,
            [*ns_params, limit, offset],
        ).fetchall()
    return rows, total


def list_namespaces() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT ns, COUNT(*) AS cnt, MAX(updated_at) AS last_updated
            FROM entries
            GROUP BY ns
            ORDER BY ns
            """
        ).fetchall()


def add_relation(from_id: int, to_id: int, rel: str) -> None:
    """Raises EntryNotFound (with the first missing id) if either endpoint doesn't exist."""
    with get_conn() as conn:
        ids = {
            r["id"]
            for r in conn.execute(
                "SELECT id FROM entries WHERE id IN (?, ?)", (from_id, to_id)
            ).fetchall()
        }
        missing = {from_id, to_id} - ids
        if missing:
            raise EntryNotFound(min(missing))
        conn.execute(
            "INSERT OR IGNORE INTO relations(from_id, to_id, rel) VALUES (?, ?, ?)",
            (from_id, to_id, rel),
        )


def remove_relation(from_id: int, to_id: int) -> int:
    """Returns the number of relation rows removed (both directions)."""
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM relations WHERE (from_id=? AND to_id=?) OR (from_id=? AND to_id=?)",
            (from_id, to_id, to_id, from_id),
        )
        return cur.rowcount


def get_relations(id: int) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT r.rel, r.from_id, r.to_id,
                   e.ns, e.key, e.title, e.updated_at,
                   CASE WHEN r.from_id = ? THEN 'outgoing' ELSE 'incoming' END AS direction
            FROM relations r
            JOIN entries e ON e.id = CASE WHEN r.from_id = ? THEN r.to_id ELSE r.from_id END
            WHERE r.from_id = ? OR r.to_id = ?
            ORDER BY r.rel, e.ns, e.key
            """,
            (id, id, id, id),
        ).fetchall()


def delete_entry(id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM entries WHERE id = ?", (id,))
        return bool(cur.rowcount)
