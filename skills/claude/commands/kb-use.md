# KB Use

## Input

$ARGUMENTS

## Instructions

Reply to the user in the language they used to ask.

Retrieve what's already known before searching the codebase. Work down the tiers and stop as soon as you have what you need — each tier is cheaper and more distilled than the one below it.

**Tier 1 — Knowledge base (`mcp-kb-sqlite`).** Cross-session, cross-repo memory: architecture decisions, non-obvious behaviors, gotchas. Tools: `list_namespaces`, `search`, `list`, `get`, `get_relations` — read each tool's description for its parameters.

- Start with `list_namespaces` to see what projects exist, unless you already know the namespace or did this earlier in the session.
- Search the relevant namespace. Namespaces match by prefix, so one word covers every subsystem under it.
- **Search the current repo's namespace first**, even when the question is framed in terms of another service — knowledge is stored under the service that _owns_ the behavior, not the one that raised the question.
- Reading across namespaces is always fine; only writes are guarded.
- **Keep queries short** — FTS5 ANDs all terms, so long queries over-filter. Use 1–3 focused keywords and run separate searches for different angles rather than one long query. English only. FTS5 operators `AND`, `OR`, `NOT` work as-is. Special characters (`.`, `-`, `(`, `)`, etc.) are fine in plain queries. Wrap in double quotes for strict phrase search — `"127.0.0.1"` or `"project-name"` matches the exact string including the special character.
- If the topic spans services, search again without the namespace filter, and check `_cross-service/`.
- `title`, `description`, `tags`, and `data` are all FTS-indexed, but search only returns a snippet — a promising entry may hold much more, so fetch it in full (`get(id, include_data=True)`) before moving on.
- Nothing found? Browse the namespace, then follow relations out from anything close.

**Tier 2 — Repo docs.** Repo-local knowledge that travels with the code — `README.md`, `docs/`, ADRs, whatever that repo keeps. Check the repo you're working in; for a cross-service question, check the other service's repo too. A tier 1 entry may point here rather than duplicating a document, so follow any file path it gives you — that's the entry working as intended, not a miss. These are version-controlled alongside the code, so on repo-local specifics they may be fresher than the global KB; prefer them where the two conflict.

**Tier 3 — Code.** Last resort. Prefer it only for details no one wrote down, or to verify something a higher tier flagged `[needs verification]` or marked stale with an old `Last verified:` date.

Treat what you find as _reported_, not proven — entries can be outdated. If a tier contradicts the code, the code wins; note the discrepancy so it can be corrected with `/kb-update`.

State which tier(s) you used.
