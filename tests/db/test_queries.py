import pytest

import mcp_kb_sqlite.db as db_module
from mcp_kb_sqlite.db import init_db, queries


@pytest.fixture(autouse=True)
def _fresh_db(monkeypatch, tmp_path):
    db_module._db_path = None
    monkeypatch.setenv("DB_PATH", str(tmp_path / "kb.db"))
    init_db()
    yield
    db_module._db_path = None


# ---------- create_entry ----------

def test_create_entry_returns_id():
    result = queries.create_entry("proj/a", "k1", "Title", "desc", ["x"], "payload")
    assert result == {"id": 1, "ns": "proj/a", "key": "k1"}


def test_create_entry_missing_required_field_raises_value_error():
    with pytest.raises(ValueError, match="ns, key, and title"):
        queries.create_entry(None, "k1", "Title", None, None, None)


def test_create_entry_clash_raises_entry_clash():
    queries.create_entry("proj/a", "k1", "Title", None, None, None)
    with pytest.raises(queries.EntryClash) as exc:
        queries.create_entry("proj/a", "k1", "Other title", None, None, None)
    assert (exc.value.ns, exc.value.key, exc.value.id) == ("proj/a", "k1", 1)


# ---------- update_entry ----------

def test_update_entry_patches_only_given_fields():
    queries.create_entry("proj/a", "k1", "Title", "desc", ["x"], "payload")
    result = queries.update_entry(1, None, None, None, "new desc", None, None)
    assert result == {"id": 1, "ns": "proj/a", "key": "k1", "changed": ["description"]}
    row = queries.get_entry(1)
    assert row["description"] == "new desc"
    assert row["title"] == "Title"


def test_update_entry_empty_string_clears_description():
    queries.create_entry("proj/a", "k1", "Title", "desc", None, None)
    queries.update_entry(1, None, None, None, "", None, None)
    assert queries.get_entry(1)["description"] is None


def test_update_entry_empty_list_clears_tags():
    queries.create_entry("proj/a", "k1", "Title", None, ["x", "y"], None)
    queries.update_entry(1, None, None, None, None, [], None)
    assert queries.get_entry(1)["tags"] is None


def test_update_entry_cannot_clear_ns_key_title():
    queries.create_entry("proj/a", "k1", "Title", None, None, None)
    with pytest.raises(ValueError, match="cannot be cleared"):
        queries.update_entry(1, "", None, None, None, None, None)


def test_update_entry_nothing_to_update_raises():
    queries.create_entry("proj/a", "k1", "Title", None, None, None)
    with pytest.raises(ValueError, match="nothing to update"):
        queries.update_entry(1, None, None, None, None, None, None)


def test_update_entry_not_found_raises():
    with pytest.raises(queries.EntryNotFound) as exc:
        queries.update_entry(999, None, None, None, "x", None, None)
    assert exc.value.id == 999


def test_update_entry_rename_clash_raises():
    queries.create_entry("proj/a", "k1", "Title1", None, None, None)
    queries.create_entry("proj/a", "k2", "Title2", None, None, None)
    with pytest.raises(queries.EntryClash) as exc:
        queries.update_entry(2, None, "k1", None, None, None, None)
    assert (exc.value.ns, exc.value.key, exc.value.id) == ("proj/a", "k1", 1)


def test_update_entry_can_rename_ns_and_key():
    queries.create_entry("proj/a", "k1", "Title", None, None, None)
    result = queries.update_entry(1, "proj/b", "k2", None, None, None, None)
    assert result["ns"] == "proj/b"
    assert result["key"] == "k2"


# ---------- get_entry ----------

def test_get_entry_returns_none_when_missing():
    assert queries.get_entry(999) is None


def test_get_entry_returns_row_when_present():
    queries.create_entry("proj/a", "k1", "Title", None, None, None)
    row = queries.get_entry(1)
    assert row["ns"] == "proj/a"
    assert row["key"] == "k1"


# ---------- search_entries ----------

def test_search_entries_finds_match():
    queries.create_entry("proj/a", "k1", "Alpha Title", "alpha description", None, None)
    queries.create_entry("proj/b", "k2", "Beta Title", "beta description", None, None)
    rows = queries.search_entries("Alpha", None, 10, 0)
    assert [r["id"] for r in rows] == [1]


def test_search_entries_filters_by_ns():
    queries.create_entry("proj/a", "k1", "Thing", None, None, None)
    queries.create_entry("other", "k2", "Thing", None, None, None)
    rows = queries.search_entries("Thing", "proj", 10, 0)
    assert [r["id"] for r in rows] == [1]


def test_search_entries_respects_limit_offset():
    for i in range(3):
        queries.create_entry("proj", f"k{i}", f"Widget {i}", None, None, None)
    rows = queries.search_entries("Widget", None, 1, 1)
    assert len(rows) == 1


# ---------- list_entries ----------

def test_list_entries_returns_all_and_total():
    queries.create_entry("proj/a", "k1", "T1", None, None, None)
    queries.create_entry("proj/b", "k2", "T2", None, None, None)
    rows, total = queries.list_entries(None, 20, 0)
    assert total == 2
    assert len(rows) == 2


def test_list_entries_filters_by_ns():
    queries.create_entry("proj/a", "k1", "T1", None, None, None)
    queries.create_entry("other", "k2", "T2", None, None, None)
    rows, total = queries.list_entries("proj", 20, 0)
    assert total == 1
    assert rows[0]["ns"] == "proj/a"


def test_list_entries_total_independent_of_limit():
    for i in range(5):
        queries.create_entry("proj", f"k{i}", f"T{i}", None, None, None)
    rows, total = queries.list_entries(None, 2, 0)
    assert total == 5
    assert len(rows) == 2


# ---------- list_namespaces ----------

def test_list_namespaces_groups_and_counts():
    queries.create_entry("proj/a", "k1", "T1", None, None, None)
    queries.create_entry("proj/b", "k2", "T2", None, None, None)
    queries.create_entry("other", "k3", "T3", None, None, None)
    rows = queries.list_namespaces()
    by_ns = {r["ns"]: r["cnt"] for r in rows}
    assert by_ns == {"proj/a": 1, "proj/b": 1, "other": 1}


# ---------- add_relation / remove_relation / get_relations ----------

def test_add_relation_creates_link():
    queries.create_entry("proj", "a", "A", None, None, None)
    queries.create_entry("proj", "b", "B", None, None, None)
    queries.add_relation(1, 2, "see_also")
    rows = queries.get_relations(1)
    assert len(rows) == 1
    assert rows[0]["direction"] == "outgoing"


def test_add_relation_missing_endpoint_raises():
    queries.create_entry("proj", "a", "A", None, None, None)
    with pytest.raises(queries.EntryNotFound) as exc:
        queries.add_relation(1, 999, "see_also")
    assert exc.value.id == 999


def test_add_relation_duplicate_is_ignored():
    queries.create_entry("proj", "a", "A", None, None, None)
    queries.create_entry("proj", "b", "B", None, None, None)
    queries.add_relation(1, 2, "see_also")
    queries.add_relation(1, 2, "see_also")
    assert len(queries.get_relations(1)) == 1


def test_remove_relation_deletes_both_directions():
    queries.create_entry("proj", "a", "A", None, None, None)
    queries.create_entry("proj", "b", "B", None, None, None)
    queries.add_relation(1, 2, "see_also")
    removed = queries.remove_relation(2, 1)  # order reversed on purpose
    assert removed == 1
    assert queries.get_relations(1) == []


def test_get_relations_labels_incoming_direction():
    queries.create_entry("proj", "a", "A", None, None, None)
    queries.create_entry("proj", "b", "B", None, None, None)
    queries.add_relation(1, 2, "see_also")
    rows = queries.get_relations(2)
    assert rows[0]["direction"] == "incoming"


def test_get_relations_empty_for_unrelated_entry():
    queries.create_entry("proj", "a", "A", None, None, None)
    assert queries.get_relations(1) == []


# ---------- replace_entry ----------

def test_replace_entry_replaces_single_match():
    queries.create_entry("proj", "a", "A", None, None, "hello world")
    result = queries.replace_entry(1, "world", "there")
    assert result == {"id": 1, "ns": "proj", "key": "a"}
    assert queries.get_entry(1)["data"] == "hello there"


def test_replace_entry_not_found_raises():
    with pytest.raises(queries.EntryNotFound) as exc:
        queries.replace_entry(999, "a", "b")
    assert exc.value.id == 999


def test_replace_entry_empty_old_string_raises():
    queries.create_entry("proj", "a", "A", None, None, "data")
    with pytest.raises(ValueError, match="must not be empty"):
        queries.replace_entry(1, "", "x")


def test_replace_entry_no_match_raises():
    queries.create_entry("proj", "a", "A", None, None, "hello world")
    with pytest.raises(ValueError, match="not found"):
        queries.replace_entry(1, "missing", "x")


def test_replace_entry_multiple_matches_without_replace_all_raises():
    queries.create_entry("proj", "a", "A", None, None, "foo foo foo")
    with pytest.raises(ValueError, match="matches 3 times"):
        queries.replace_entry(1, "foo", "bar")


def test_replace_entry_replace_all_replaces_every_occurrence():
    queries.create_entry("proj", "a", "A", None, None, "foo foo foo")
    queries.replace_entry(1, "foo", "bar", replace_all=True)
    assert queries.get_entry(1)["data"] == "bar bar bar"


# ---------- delete_entry ----------

def test_delete_entry_returns_true_when_deleted():
    queries.create_entry("proj", "a", "A", None, None, None)
    assert queries.delete_entry(1) is True
    assert queries.get_entry(1) is None


def test_delete_entry_returns_false_when_missing():
    assert queries.delete_entry(999) is False


def test_delete_entry_cascades_relations():
    queries.create_entry("proj", "a", "A", None, None, None)
    queries.create_entry("proj", "b", "B", None, None, None)
    queries.add_relation(1, 2, "see_also")
    queries.delete_entry(1)
    assert queries.get_relations(2) == []
