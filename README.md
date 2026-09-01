# mcp-kb-sqlite

Simple, fast persistent memory for your coding agent — cross-session, cross-project. One knowledge
base shared across every repo you work in, so what you learn in one project is there the next time
you open another. Entries can be linked to each other (`relate`), so related facts stay connected
instead of scattered.

Start a conversation with `/kb-use` to load relevant context before you begin. When you learn
something worth keeping — an architecture decision, a gotcha, a debugging finding — save it with
`/kb-update`.

Under the hood: a plain SQLite database with an FTS5 full-text index, and a small tool surface for
agents to search, save, and link entries. No server to run, no external service, no schema to
manage by hand.

## Install — MCP server

The database lives at `~/.ai-memory/kb.db` unless you override it with `DB_PATH` (shown below,
optional). The schema is created and migrated automatically on first connection.

### Claude Code

```sh
claude mcp add kb -- uv run --directory /path/to/mcp-kb-sqlite mcp-kb-sqlite

# with a custom DB_PATH:
claude mcp add kb --env DB_PATH=/path/to/kb.db -- uv run --directory /path/to/mcp-kb-sqlite mcp-kb-sqlite
```

Or add it directly to `.mcp.json` (project-local) or `~/.claude.json` (user-scoped, under the
top-level `mcpServers` key):

```json
{
  "mcpServers": {
    "kb": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mcp-kb-sqlite", "mcp-kb-sqlite"],
      "env": { "DB_PATH": "/path/to/kb.db" }
    }
  }
}
```

`env` is optional — drop it to use the default `~/.ai-memory/kb.db`.

### OpenCode

Add to `opencode.json` (global at `~/.config/opencode/opencode.json`, or project-local):

```json
{
  "mcp": {
    "kb": {
      "type": "local",
      "command": [
        "uv",
        "run",
        "--directory",
        "/path/to/mcp-kb-sqlite",
        "mcp-kb-sqlite"
      ],
      "enabled": true,
      "environment": { "DB_PATH": "/path/to/kb.db" }
    }
  }
}
```

`environment` is optional — drop it to use the default `~/.ai-memory/kb.db`.

## Install — skills

The `/kb-use` and `/kb-update` workflows ship as skills for both Claude Code and OpenCode. The two
flavors are hand-kept in sync — there's no generator, so edit both when instructions change.

### Claude Code

Copy or symlink `skills/claude/commands/*.md` into `~/.claude/commands/`.

### OpenCode

Copy or symlink each `skills/opencode/<name>/` directory into `~/.config/opencode/skills/<name>/`
(or a project-local `.opencode/skills/`). OpenCode skills are auto-invoked by description match via
the agent's `skill` tool, but can also be triggered directly as `/<name>` in chat — this prepends
the SKILL.md text and appends whatever you typed after the command.

## Tools

| Tool                                                       | Purpose                                                       |
| ---------------------------------------------------------- | ------------------------------------------------------------- |
| `save(id?, ns?, key?, title?, description?, tags?, data?)` | Create or update an entry — see below                         |
| `replace(id, old_string, new_string, replace_all=False)`   | Targeted edit to an entry's `data` — see below                |
| `get(id, include_data=False)`                              | Fetch one entry; `include_data=True` returns the payload      |
| `search(query, ns?, limit=10, offset=0)`                   | FTS5/BM25 over title + description + tags + data              |
| `list(ns?, limit=20, offset=0)`                            | Entries by recency, metadata only                             |
| `list_namespaces()`                                        | Namespaces with entry counts and last-updated date            |
| `relate(from_id, to_id, rel?)`                             | Link two entries; omit `rel` to remove all links between them |
| `get_relations(id)`                                        | Links in both directions                                      |
| `delete(id)`                                               | Remove an entry (cascades to its relations)                   |

Entries are addressed by `ns` (namespace, e.g. `project/subsystem`) plus `key` (a slug unique within the
namespace). `ns` filters are prefix matches, so `ns="project"` covers every subsystem under it.

`title`, `description`, `tags`, and `data` are all FTS-indexed — `search` matches against the full
entry, including its payload, not just the summary fields.

### `save`: create vs. update

Every parameter is optional; the presence of `id` picks the mode.

**Update** — pass `id` plus only the fields you want to change:

```python
save(id=42, description="new search hints")   # title, tags, data untouched
```

Omitted fields keep their current value. Pass `""` (or `[]` for `tags`) to clear `description`, `tags`, or
`data`. `ns`, `key`, and `title` can be changed — that's how you rename or move an entry — but not cleared.

**Create** — omit `id`; `ns`, `key`, and `title` are all required:

```python
save(ns="project/db", key="schema", title="Schema layout", tags=["db","schema"], data="…")
```

There is no upsert. Creating over an existing `(ns, key)` is an error that reports the existing id, so an
accidental full overwrite isn't possible:

```
Error: project/db/schema already exists (id=42) — pass id=42 to update it
```

### `replace`: targeted edits without resending `data`

For a small change to an existing entry's `data`, `replace` avoids resending the whole field through `save`:

```python
replace(id=42, old_string="old fact", new_string="corrected fact")
```

`old_string` must match exactly. It's an error if the text isn't found, or if it matches more than once —
pass `replace_all=True` to replace every occurrence, or include more surrounding context in `old_string` to
disambiguate a single occurrence. This mirrors editor-style find/replace: self-verifying, so a stale or
ambiguous call fails loudly instead of silently writing to the wrong content.
