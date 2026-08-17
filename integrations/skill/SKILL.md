---
name: engram
description: Use Engram when the user says "remember this", asks what was previously decided, or requests recall of prior preferences, failures, decisions, or project history.
---

# Shared Agent Memory

Use the local shared memory repository as the durable cross-agent brain. Keep this workflow vendor-neutral: run the installed `engram` CLI and use ordinary filesystem reads rather than platform-specific tools.

## Route the request

- Route a plain "remember this" request to this shared agent brain.
- Ask immediately when the destination, intended fact, note type, or scope is ambiguous. Do not guess and write.

## Recall before answering

Recall prior decisions, preferences, failures, and project history whenever they could affect the answer:

```sh
engram recall "QUERY" --corpus all --json
```

Only a confirmed local note is truth. Treat external corpus results as labeled,
noncanonical evidence. Ignore inferred, conflicted, and superseded local notes
as truth.

Open the full Markdown page identified by a relevant result before relying on it. Never answer from a search snippet alone. If confirmed notes conflict in meaning, state the ambiguity and ask immediately rather than selecting one silently.

## Remember explicitly requested information

Choose the narrowest applicable type: `preference`, `decision`, `project_state`, `environment`, `pattern`, `failure`, or `fact`. Preserve the user's meaning without adding deductions.

```sh
printf '%s\n' "MEMORY" | engram remember --type TYPE --stdin --json
```

Report what was stored. Never include credentials, private reasoning, or an entire transcript.

## Correct or forget

Replace outdated truth through the correction command so history remains explicit:

```sh
printf '%s\n' "CORRECTED MEMORY" | engram correct NOTE_ID --stdin --json
engram forget NOTE_ID --reason "REASON" --json
```

Do not edit canonical note files directly.

## Open actions (warm memory)

`warm.md` at the repository root is an optional, hand-curated list of open items. Edit it with ordinary file tools; the CLI never rewrites it, and it is not injected at session start — read it on demand.

- When the user asks what is open, pending, or worth working on, read `warm.md` and report the entries.
- Add an entry when a durable open item emerges. First line format: `- **Title** (imp N[, due YYYY-MM-DD]):` — `imp` is importance 1–5 (default 3), `due` is optional. Keep entries short and link the canonical note id when one exists.
- Nightly maintenance sorts entries by descending score — 60% deadline urgency, 40% importance — and promotes anything due within 14 days, or already overdue, into `hot.md` as an `[urgent]` line. Don't hand-sort; set `imp` and `due` correctly and let maintenance order them.
- Update an entry in place as things move; delete it only when the item is fully closed.

Worked examples of every importance level, with and without deadlines, are in `warm.md.example`.

## Session capture boundary

Treat automatic post-session capture as pending evidence only. It remains unpromoted and must not become canonical truth unless the user later confirms it through an explicit memory action.
