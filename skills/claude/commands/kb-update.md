# KB Update

## Input

$ARGUMENTS

**If the user gave an explicit instruction above, follow it first** — including storing into another project's namespace. The namespace guards below apply to autonomous decisions only, not to direct requests.

## Instructions

Reply to the user in the language they used to ask.

Save what you've learned using the `mcp-kb-sqlite` MCP server: `search`, `list`, `list_namespaces`, `get`, `save`, `relate`, `get_relations`, `delete`. Read each tool's own description for its parameters and semantics — this document covers only judgment the tools can't encode.

1. **Decide what to store.** Rule of thumb: _"Will this help a fresh agent understand the project in 3 months?"_
   - Store: architecture decisions, non-obvious behaviors, integration patterns, gotchas.
   - Skip only pure ephemera: things already in code/docs, details with no reuse value.
   - A "one-time fix" often hides a non-obvious behavior — store the behavior, drop the ticket specifics.
   - **Task entries** are acceptable scaffolding for an active complex task spanning multiple repos (cross-service coordination, a running gotcha list, in-flight status). Use a key like `<TICKET>-status` and mark `status: IN_PROGRESS` in `data`. They are temporary by construction — see housekeeping.
   - When in doubt, store — a flagged imperfect fact beats a missing one.

2. **Choose namespace** — `service/subsystem` format. Namespace by the service that owns the behavior, not the one that triggered the investigation.
   - Integration facts (how _this_ service calls service B) → **current** namespace.
   - Pure internals of service B found incidentally → foreign namespace + thin `see_also` entry in current namespace.
   - Updating a foreign entry → do it + thin cross-reference in current namespace.
   - Facts spanning two+ services → `_cross-service/`, then relate to both.
   - An autonomous finding about a project you're not working in is still worth storing — just flag it in your reply ("Stored under `ns/key`"). Ask first only if you're unsure it's correct.

3. **Check existing** — before writing, actively look for duplicates:
   - Browse the namespace, and paginate if the listing reports more entries than it showed.
   - Run **2–3 searches from different angles** — vary the wording, try synonyms and related concepts. A single query often misses entries phrased differently.

4. **Write or update** — treat the KB as a living document, not an append-only log:
   - If a matching entry exists → update it in place, sending only the fields that change.
   - If the knowledge fits better as part of an existing entry → extend that entry, don't create a new one.
   - If nothing matches → create a new entry. English always.
   - **Put multi-line content in the `data` field — schemas, code, SQL, configs, stack traces, long docs. Do not skip it to save tokens.** The indexed fields (`title`/`description`/`tags`) are for finding the entry; `data` holds the actual knowledge. (`data` is not FTS-indexed — reload `save`'s schema via ToolSearch if you're unsure of a field name, don't rely on prose here.)
   - **If the repo already documents it (`README.md`, `docs/`, ADRs), link to it — don't copy it in.** Put the file path plus a short summary in `data` instead of the document's contents. The doc stays canonical and maintained where it lives; the entry's job is to make it findable, since only the indexed fields drive search. Write a real summary rather than a bare path, so the entry still says something if the file moves.
   - Being told the entry already exists means step 3 missed a duplicate — re-read that entry and update it, don't work around the error.
   - Mark time-sensitive facts `Last verified: YYYY-MM-DD`; uncertain ones `[needs verification]`.

5. **Housekeeping (when it pays off):**
   - Decompose completed task entries — extract each non-obvious behavior or gotcha into a focused standalone entry under the owning service's namespace, then delete the task entry. Do this as soon as you spot one whose work is done; don't defer it, and never leave a finished task as a permanent record.
   - Consolidate overlapping entries. Update or delete stale ones you noticed during the session.
   - Relate strongly-connected entries. `relate(from_id, to_id, rel)` defaults `rel` to `see_also` when omitted — pass `rel` explicitly (`see_also`, `part_of`, `caused_by`, `example_of`) when adding a link. To remove a relation, pass `rel=null` explicitly — that's the only way to delete.

Confirm what you stored (ns/key).
