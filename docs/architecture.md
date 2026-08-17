# Architecture

## Canonical Markdown, disposable SQLite

Markdown notes are Engram's durable record. They are readable without Engram,
easy to audit, and retain correction history in ordinary files. SQLite exists
only to accelerate retrieval: the FTS5 database, WAL, and SHM files under
`state/` may be deleted and rebuilt from Markdown at any time.

Each note has frontmatter containing an identifier, one of seven types
(`preference`, `decision`, `project_state`, `environment`, `pattern`, `failure`,
or `fact`), a truth status, timestamps, source references, and tags. The body
holds the durable memory. Status is one of `confirmed`, `inferred`,
`conflicted`, or `superseded`.

## Write path

Writes take a repository-wide advisory `fcntl` lock. Engram writes the complete
new content to a temporary file in the destination directory, flushes and
`fsync`s that file, atomically renames it over the destination, and then
`fsync`s the parent directory. Readers therefore see either the old complete
file or the new complete file, never a partial write.

## Corrections and recovery

A correction is replacement-first. Engram writes the new confirmed note before
marking the old note `superseded`, recording the transition in a durable
correction journal. Recovery runs before recall, status, and maintenance. If a
process stops between those writes, recovery completes the transition before a
reader can observe two canonical truths.

## Index lifecycle

Reconciliation scans canonical notes and registered corpora, updates changed
documents, and removes vanished documents. Integrity failures cause the SQLite
files to be quarantined with a timestamped corruption suffix, after which the
index is rebuilt from Markdown. No durable truth depends on the database.

Lexical retrieval uses FTS5 BM25. When a compatible local semantic model is
available, Engram computes cosine-similarity ranks and combines them with the
lexical ranks through reciprocal rank fusion. If semantic ranking is
unavailable or fails, retrieval falls back to FTS5.

## Corpus model

The reserved corpus name `local` identifies the canonical Engram store.
Additional named corpora are declared in `engram.toml` and indexed read-only.
Their results are labeled noncanonical evidence: Engram never writes to those
paths and never treats them as local confirmed truth.
