"""End-to-end walk through every tool against a real (temp-file) SQLite database.

Unlike tests/db/test_queries.py (unit tests on the DB layer) and tests/test_server.py
(unit tests on server.py with queries mocked), this exercises the full stack — init_db()
through the public @mcp.tool() functions in server.py — the same way an agent actually
calls them, one after another, checking each step's output before moving to the next.
"""

import pytest

import mcp_kb_sqlite.db as db_module
from mcp_kb_sqlite.db import init_db
from mcp_kb_sqlite.server import (
    delete,
    get,
    get_relations,
    list,
    list_namespaces,
    relate,
    save,
    search,
)


@pytest.fixture(autouse=True)
def _fresh_db(monkeypatch, tmp_path):
    db_module._db_path = None
    monkeypatch.setenv("DB_PATH", str(tmp_path / "kb.db"))
    init_db()
    yield
    db_module._db_path = None


def test_full_lifecycle():
    # 1. Empty database.
    assert list_namespaces() == "No namespaces found."
    assert list() == "No entries found."
    assert search("anything") == "No results."

    # 2. Create two entries in different namespaces.
    created_a = save(
        ns="proj/backend", key="auth-flow", title="Auth flow overview",
        description="OAuth token refresh and session handling",
        tags=["auth", "oauth"], data="detailed design notes",
    )
    assert created_a == "Created: proj/backend/auth-flow (id=1)"

    created_b = save(
        ns="proj/frontend", key="auth-ui", title="Login screen",
        description="Login form and OAuth redirect UI",
        tags=["auth", "ui"],
    )
    assert created_b == "Created: proj/frontend/auth-ui (id=2)"

    # 3. Creating over the same (ns, key) fails with a clean, actionable error.
    clash = save(ns="proj/backend", key="auth-flow", title="Duplicate")
    assert clash == "Error: proj/backend/auth-flow already exists (id=1) — pass id=1 to update it"

    # 4. list_namespaces shows both, grouped under their common "proj" root.
    ns_listing = list_namespaces()
    assert "proj/backend (1)" in ns_listing
    assert "proj/frontend (1)" in ns_listing

    # 5. list() shows both entries with a total footer.
    listing = list()
    assert "proj/backend/auth-flow" in listing
    assert "proj/frontend/auth-ui" in listing
    assert "(2 total)" in listing

    # 6. list(ns=...) filters by namespace prefix.
    backend_only = list(ns="proj/backend")
    assert "auth-flow" in backend_only
    assert "auth-ui" not in backend_only

    # 7. search() finds both via the shared "OAuth" keyword.
    oauth_hits = search("OAuth")
    assert "auth-flow" in oauth_hits
    assert "auth-ui" in oauth_hits

    # 8. search(ns=...) narrows to one namespace.
    frontend_hits = search("OAuth", ns="proj/frontend")
    assert "auth-ui" in frontend_hits
    assert "auth-flow" not in frontend_hits

    # 9. get() without include_data omits the payload; with it, includes it.
    brief = get(1)
    assert "detailed design notes" not in brief
    assert "Auth flow overview" in brief

    full = get(1, include_data=True)
    assert "detailed design notes" in full

    # 10. get() on a missing id.
    assert get(999) == "Not found: id=999"

    # 11. Update entry 2 — patch description only, leave title/tags untouched.
    updated = save(id=2, description="Login form, OAuth redirect UI, and error states")
    assert updated == "Updated: proj/frontend/auth-ui (id=2) — fields: description"
    assert "error states" in get(2, include_data=False)

    # 12. relate() links the two entries.
    linked = relate(1, 2, rel="see_also")
    assert linked == "Related 1 --[see_also]--> 2"

    # 13. get_relations() shows both directions from either side.
    from_1 = get_relations(1)
    assert "[see_also] --> id=2" in from_1
    from_2 = get_relations(2)
    assert "[see_also] <-- id=1" in from_2

    # 14. relate() to a nonexistent id fails cleanly, no partial state.
    assert relate(1, 999) == "Not found: id=999"

    # 15. Unrelate removes the link in both directions.
    unlinked = relate(1, 2, rel=None)
    assert unlinked == "Unrelated 1 <--> 2 (1 removed)"
    assert get_relations(1) == "No relations found for id=1"

    # 16. delete() removes an entry; a second delete reports not found.
    assert delete(2) == "Deleted id=2"
    assert delete(2) == "Not found: id=2"
    assert get(2) == "Not found: id=2"

    # 17. Final state: only entry 1 remains.
    final_listing = list()
    assert "auth-flow" in final_listing
    assert "auth-ui" not in final_listing
    assert "(1 total)" in final_listing


def test_delete_cascades_relations_end_to_end():
    save(ns="t", key="a", title="A")
    save(ns="t", key="b", title="B")
    relate(1, 2)

    assert delete(1) == "Deleted id=1"

    assert get_relations(2) == "No relations found for id=2"
