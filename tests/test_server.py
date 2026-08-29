from unittest.mock import patch

from mcp_kb_sqlite.db import queries
from mcp_kb_sqlite.server import (
    delete,
    get,
    get_relations,
    list,
    list_namespaces,
    relate,
    replace,
    save,
    search,
)

# ---------- save (create) ----------

def test_save_create_success():
    with patch(
        "mcp_kb_sqlite.server.queries.create_entry",
        return_value={"id": 1, "ns": "proj/a", "key": "k1"},
    ) as m:
        result = save(ns="proj/a", key="k1", title="Title", description="d")
    m.assert_called_once_with("proj/a", "k1", "Title", "d", None, None)
    assert result == "Created: proj/a/k1 (id=1)"


def test_save_create_value_error_becomes_error_message():
    with patch(
        "mcp_kb_sqlite.server.queries.create_entry",
        side_effect=ValueError("create requires ns, key, and title (or pass id to update)"),
    ):
        result = save(title="only title")
    assert result == "Error: create requires ns, key, and title (or pass id to update)"


def test_save_create_clash_becomes_error_message():
    with patch(
        "mcp_kb_sqlite.server.queries.create_entry",
        side_effect=queries.EntryClash("proj/a", "k1", 5),
    ):
        result = save(ns="proj/a", key="k1", title="T")
    assert result == "Error: proj/a/k1 already exists (id=5) — pass id=5 to update it"


# ---------- save (update) ----------

def test_save_update_success():
    with patch(
        "mcp_kb_sqlite.server.queries.update_entry",
        return_value={"id": 1, "ns": "proj/a", "key": "k1", "changed": ["description"]},
    ) as m:
        result = save(id=1, description="new")
    m.assert_called_once_with(1, None, None, None, "new", None, None)
    assert result == "Updated: proj/a/k1 (id=1) — fields: description"


def test_save_update_not_found_becomes_error_message():
    with patch(
        "mcp_kb_sqlite.server.queries.update_entry",
        side_effect=queries.EntryNotFound(7),
    ):
        result = save(id=7, description="x")
    assert result == "Not found: id=7"


def test_save_update_clash_becomes_error_message():
    with patch(
        "mcp_kb_sqlite.server.queries.update_entry",
        side_effect=queries.EntryClash("proj/a", "k1", 3),
    ):
        result = save(id=1, key="k1")
    assert result == "Error: proj/a/k1 already exists (id=3) — pass id=3 to update it"


def test_save_dispatches_to_create_when_id_is_none():
    with patch("mcp_kb_sqlite.server.queries.create_entry") as create, patch(
        "mcp_kb_sqlite.server.queries.update_entry"
    ) as update:
        create.return_value = {"id": 1, "ns": "n", "key": "k"}
        save(ns="n", key="k", title="T")
    create.assert_called_once()
    update.assert_not_called()


def test_save_dispatches_to_update_when_id_given():
    with patch("mcp_kb_sqlite.server.queries.create_entry") as create, patch(
        "mcp_kb_sqlite.server.queries.update_entry"
    ) as update:
        update.return_value = {"id": 1, "ns": "n", "key": "k", "changed": ["title"]}
        save(id=1, title="T")
    update.assert_called_once()
    create.assert_not_called()


# ---------- get ----------

def test_get_not_found():
    with patch("mcp_kb_sqlite.server.queries.get_entry", return_value=None):
        assert get(999) == "Not found: id=999"


def test_get_formats_row_without_data_by_default():
    row = {
        "id": 1, "ns": "proj/a", "key": "k1", "title": "Title",
        "description": "Desc", "tags": '["x", "y"]', "data": "payload",
        "created_at": "2026-08-28 00:00:00", "updated_at": "2026-08-28 00:00:00",
    }
    with patch("mcp_kb_sqlite.server.queries.get_entry", return_value=row):
        result = get(1)
    assert "payload" not in result
    assert "tags=['x', 'y']" in result
    assert "Desc" in result


def test_get_includes_data_when_requested():
    row = {
        "id": 1, "ns": "proj/a", "key": "k1", "title": "Title",
        "description": None, "tags": None, "data": "payload",
        "created_at": "2026-08-28 00:00:00", "updated_at": "2026-08-28 00:00:00",
    }
    with patch("mcp_kb_sqlite.server.queries.get_entry", return_value=row):
        result = get(1, include_data=True)
    assert "payload" in result


# ---------- search ----------

def test_search_no_results():
    with patch("mcp_kb_sqlite.server.queries.search_entries", return_value=[]):
        assert search("nothing") == "No results."


def test_search_formats_rows():
    rows = [
        {"id": 1, "ns": "proj/a", "key": "k1", "title": "Title", "updated_at": "2026-08-28", "snip": "**hit**"},
    ]
    with patch("mcp_kb_sqlite.server.queries.search_entries", return_value=rows):
        result = search("hit")
    assert "id=1 | proj/a/k1" in result
    assert "**hit**" in result


def test_search_caps_limit_at_100():
    with patch("mcp_kb_sqlite.server.queries.search_entries", return_value=[]) as m:
        search("q", limit=500)
    assert m.call_args[0][2] == 100


# ---------- list ----------

def test_list_no_entries():
    with patch("mcp_kb_sqlite.server.queries.list_entries", return_value=([], 0)):
        assert list() == "No entries found."


def test_list_shows_total_when_all_shown():
    rows = [{"id": 1, "ns": "n", "key": "k", "title": "T", "updated_at": "2026-08-28"}]
    with patch("mcp_kb_sqlite.server.queries.list_entries", return_value=(rows, 1)):
        result = list()
    assert "(1 total)" in result


def test_list_shows_offset_hint_when_more_remain():
    rows = [{"id": 1, "ns": "n", "key": "k", "title": "T", "updated_at": "2026-08-28"}]
    with patch("mcp_kb_sqlite.server.queries.list_entries", return_value=(rows, 5)):
        result = list(limit=1)
    assert "1 of 5" in result
    assert "offset=1" in result


def test_list_caps_limit_at_100():
    with patch("mcp_kb_sqlite.server.queries.list_entries", return_value=([], 0)) as m:
        list(limit=500)
    assert m.call_args[0][1] == 100


# ---------- list_namespaces ----------

def test_list_namespaces_empty():
    with patch("mcp_kb_sqlite.server.queries.list_namespaces", return_value=[]):
        assert list_namespaces() == "No namespaces found."


def test_list_namespaces_blank_line_between_top_level_groups():
    rows = [
        {"ns": "proj/a", "cnt": 1, "last_updated": "2026-08-28"},
        {"ns": "proj/b", "cnt": 2, "last_updated": "2026-08-27"},
        {"ns": "other", "cnt": 1, "last_updated": "2026-08-26"},
    ]
    with patch("mcp_kb_sqlite.server.queries.list_namespaces", return_value=rows):
        result = list_namespaces()
    lines = result.split("\n")
    assert lines[0].startswith("proj/a")
    assert lines[1].startswith("proj/b")
    assert lines[2] == ""
    assert lines[3].startswith("other")


# ---------- relate ----------

def test_relate_add_success():
    with patch("mcp_kb_sqlite.server.queries.add_relation") as m:
        result = relate(1, 2)
    m.assert_called_once_with(1, 2, "see_also")
    assert result == "Related 1 --[see_also]--> 2"


def test_relate_add_not_found():
    with patch(
        "mcp_kb_sqlite.server.queries.add_relation",
        side_effect=queries.EntryNotFound(999),
    ):
        result = relate(1, 999)
    assert result == "Not found: id=999"


def test_relate_remove():
    with patch("mcp_kb_sqlite.server.queries.remove_relation", return_value=1) as m:
        result = relate(1, 2, rel=None)
    m.assert_called_once_with(1, 2)
    assert result == "Unrelated 1 <--> 2 (1 removed)"


# ---------- get_relations ----------

def test_get_relations_empty():
    with patch("mcp_kb_sqlite.server.queries.get_relations", return_value=[]):
        assert get_relations(1) == "No relations found for id=1"


def test_get_relations_formats_outgoing_and_incoming():
    rows = [
        {"rel": "see_also", "from_id": 1, "to_id": 2, "ns": "n", "key": "b",
         "title": "B", "updated_at": "2026-08-28", "direction": "outgoing"},
        {"rel": "part_of", "from_id": 3, "to_id": 1, "ns": "n", "key": "c",
         "title": "C", "updated_at": "2026-08-28", "direction": "incoming"},
    ]
    with patch("mcp_kb_sqlite.server.queries.get_relations", return_value=rows):
        result = get_relations(1)
    assert "--> id=2" in result
    assert "<-- id=3" in result


# ---------- replace ----------

def test_replace_success():
    with patch(
        "mcp_kb_sqlite.server.queries.replace_entry",
        return_value={"id": 1, "ns": "proj/a", "key": "k1"},
    ) as m:
        result = replace(1, "old", "new")
    m.assert_called_once_with(1, "old", "new", False)
    assert result == "Replaced in: proj/a/k1 (id=1)"


def test_replace_not_found_becomes_error_message():
    with patch(
        "mcp_kb_sqlite.server.queries.replace_entry",
        side_effect=queries.EntryNotFound(999),
    ):
        result = replace(999, "old", "new")
    assert result == "Not found: id=999"


def test_replace_value_error_becomes_error_message():
    with patch(
        "mcp_kb_sqlite.server.queries.replace_entry",
        side_effect=ValueError("old_string not found in id=1"),
    ):
        result = replace(1, "old", "new")
    assert result == "Error: old_string not found in id=1"


# ---------- delete ----------

def test_delete_success():
    with patch("mcp_kb_sqlite.server.queries.delete_entry", return_value=True):
        assert delete(1) == "Deleted id=1"


def test_delete_not_found():
    with patch("mcp_kb_sqlite.server.queries.delete_entry", return_value=False):
        assert delete(999) == "Not found: id=999"
