import json

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.utilities.func_metadata import ArgModelBase
from pydantic import ConfigDict

from mcp_kb_sqlite.db import init_db, queries

# Tool argument models otherwise silently drop unknown fields (pydantic's default
# extra="ignore"), so a misnamed param (e.g. "payload" instead of "data") looks
# like a successful call instead of erroring. Forbid extras for every @mcp.tool()
# defined below — must run before those decorators execute.
ArgModelBase.model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

mcp = MCPServer("mcp-kb-sqlite", instructions="Project knowledge base — search here before querying external sources; store cross-service architecture facts, investigation findings, and patterns worth preserving across sessions. Tools: search, save, get, list, relate, delete.")


def _fmt_date(ts: str | None) -> str:
    return ts[:10] if ts else "?"


@mcp.tool()
def save(
    id: int | None = None,
    ns: str | None = None,
    key: str | None = None,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    data: str | None = None,
) -> str:
    """Create or update a KB entry. Two modes:
    UPDATE — pass id plus only the fields you want to change. Omitted fields keep their current
    value; pass "" (or [] for tags) to clear description/tags/data. ns/key/title can be changed
    but not cleared. Errors if no entry has that id.
    CREATE — omit id and pass ns, key, and title (all three required). Errors if ns+key is taken;
    the error reports the existing id so you can re-issue it as an update.
    ns = namespace like 'project/subsystem', key = unique slug within ns.
    title: short label (FTS-indexed). description: search-hint field — write the keywords/synonyms
    a user would actually query here, not just a prose summary (FTS-indexed).
    tags: 3-5 keywords (FTS-indexed). data: large payload, NOT FTS-indexed — anything you want
    findable must appear in title, description, or tags instead. Retrieved via get()."""
    try:
        if id is None:
            result = queries.create_entry(ns, key, title, description, tags, data)
            return f"Created: {result['ns']}/{result['key']} (id={result['id']})"
        result = queries.update_entry(id, ns, key, title, description, tags, data)
        changed = ", ".join(result["changed"])
        return f"Updated: {result['ns']}/{result['key']} (id={result['id']}) — fields: {changed}"
    except ValueError as e:
        return f"Error: {e}"
    except queries.EntryNotFound as e:
        return f"Not found: id={e.id}"
    except queries.EntryClash as e:
        return f"Error: {e.ns}/{e.key} already exists (id={e.id}) — pass id={e.id} to update it"


@mcp.tool()
def get(id: int, include_data: bool = False) -> str:
    """Fetch a KB entry by id. Returns title, description, tags, and dates by default.
    Pass include_data=True to also retrieve the data payload."""
    row = queries.get_entry(id)
    if not row:
        return f"Not found: id={id}"
    tags = json.loads(row["tags"]) if row["tags"] else []
    tags_str = f"  tags={tags}" if tags else ""
    desc_str = f"\n{row['description']}" if row["description"] else ""
    header = (
        f"id={row['id']} | {row['ns']}/{row['key']}{tags_str}"
        f"  created: {_fmt_date(row['created_at'])}  updated: {_fmt_date(row['updated_at'])}\n"
        f"{row['title']}{desc_str}"
    )
    if include_data and row["data"]:
        return f"{header}\n\n{row['data']}"
    return header


@mcp.tool()
def search(
    query: str,
    ns: str | None = None,
    limit: int = 10,
    offset: int = 0,
) -> str:
    """Full-text search over entries using FTS5/BM25. Searches title, description, and tags.
    Optionally filter by ns prefix. FTS5 operators AND, OR, NOT work as-is. Wrap query in double quotes for strict phrase search — special characters (dots, hyphens, etc.) become literals inside quotes, e.g. "127.0.0.1"."""
    limit = min(limit, 100)
    rows = queries.search_entries(query, ns, limit, offset)

    if not rows:
        return "No results."

    lines = []
    for r in rows:
        lines.append(f"id={r['id']} | {r['ns']}/{r['key']}  updated: {_fmt_date(r['updated_at'])}")
        lines.append(f"  {r['title']}")
        if r["snip"]:
            lines.append(f"  {r['snip']}")
    return "\n".join(lines)


@mcp.tool()
def list(
    ns: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> str:
    """List entries (id, ns/key, title, updated_at). Optionally filter by ns prefix."""
    limit = min(limit, 100)
    rows, total = queries.list_entries(ns, limit, offset)

    if not rows:
        return "No entries found."

    lines = [
        f"id={r['id']} | {r['ns']}/{r['key']} | {r['title']} | {_fmt_date(r['updated_at'])}"
        for r in rows
    ]
    shown_end = offset + len(rows)
    if total > shown_end:
        lines.append(f"({shown_end} of {total} — use offset={shown_end} for more)")
    else:
        lines.append(f"({total} total)")
    return "\n".join(lines)


@mcp.tool()
def list_namespaces() -> str:
    """List all namespaces with entry counts and last-updated date.
    Use this first to discover available projects/topics before calling search or list."""
    rows = queries.list_namespaces()

    if not rows:
        return "No namespaces found."

    lines = []
    prev_top = None
    for r in rows:
        top = r["ns"].split("/")[0]
        if top != prev_top:
            if prev_top is not None:
                lines.append("")
            prev_top = top
        lines.append(f"{r['ns']} ({r['cnt']}) {_fmt_date(r['last_updated'])}")
    return "\n".join(lines)


@mcp.tool()
def relate(from_id: int, to_id: int, rel: str | None = "see_also") -> str:
    """Create or remove a typed relation between two entries.
    rel given or omitted (default: see_also) → add relation (INSERT OR IGNORE). Not validated —
    pick freely, but prefer these for consistency: see_also, part_of, caused_by, example_of.
    rel explicitly null → delete all relations between the pair (both directions)."""
    if rel is not None:
        try:
            queries.add_relation(from_id, to_id, rel)
        except queries.EntryNotFound as e:
            return f"Not found: id={e.id}"
        return f"Related {from_id} --[{rel}]--> {to_id}"
    removed = queries.remove_relation(from_id, to_id)
    return f"Unrelated {from_id} <--> {to_id} ({removed} removed)"


@mcp.tool()
def get_relations(id: int) -> str:
    """Get all entries related to a given entry id (both directions)."""
    rows = queries.get_relations(id)

    if not rows:
        return f"No relations found for id={id}"

    lines = [f"Relations for id={id}:"]
    for r in rows:
        arrow = "-->" if r["direction"] == "outgoing" else "<--"
        other_id = r["to_id"] if r["direction"] == "outgoing" else r["from_id"]
        lines.append(
            f"  [{r['rel']}] {arrow} id={other_id} | {r['ns']}/{r['key']} — {r['title']}"
            f"  (updated: {_fmt_date(r['updated_at'])})"
        )
    return "\n".join(lines)


@mcp.tool()
def delete(id: int) -> str:
    """Delete a KB entry by id."""
    if queries.delete_entry(id):
        return f"Deleted id={id}"
    return f"Not found: id={id}"


def main() -> None:
    init_db()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
