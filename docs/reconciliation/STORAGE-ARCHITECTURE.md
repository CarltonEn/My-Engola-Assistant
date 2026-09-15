# Engola Storage Architecture — Spec

Written for a phone-constrained (Termux) deployment where disk space,
battery, and network reliability are real constraints, not edge cases.

## Why this exists

Engola downloads and generates files continuously: PDFs pulled in for
knowledge ingestion, YouTube transcripts, generated notes, career
documents, voice narration scripts. Without a deliberate storage design,
a phone running Termux will silently fill its disk, and nobody — owner
or agent — will be able to answer "what does Engola actually have, and
why." This spec gives every file a single lifecycle: identified by
content, tiered by usage, and always traceable.

## 1. Three tiers, one identity per file

Every piece of content is identified by its **SHA-256 hash**, not by
filename or path. The same bytes are only ever stored once, anywhere.

| Tier | What lives here | Where |
|---|---|---|
| **Hot** | Recently-used file bytes | Local disk (`data/blobs/`, sharded by hash prefix) |
| **Warm** | Searchable index: extracted text, embeddings, chat/task/memory records | SQLite now → Postgres/Supabase later |
| **Cold** | Original large files, kept indefinitely | External archive (Telegram, S3, anything) — Engola stores only a pointer |

A file's row in the `blobs` table never disappears when it moves tiers —
only `tier` and `local_path` change. The metadata (hash, filename, size,
category, provenance) is permanent even after the bytes are evicted
locally, because a cold pointer is worthless without it.

## 2. Content-addressable storage + dedup

Before anything is written to disk, its SHA-256 is computed. If that
hash already has a row, the new write becomes a no-op that just bumps
`last_accessed_at` and `access_count` — no duplicate bytes are ever
written. This matters more on a phone than on a server: the same PDF
downloaded twice, or the same YouTube audio re-processed, should cost
zero extra storage.

## 3. Eviction is opt-in-by-proof, not by age alone

A blob is only ever deleted locally if it **already has a registered
cold-archive pointer** (`archive_provider` + at least one of
`archive_identifier` / `archive_file_id` / `archive_url`). Age and access
count decide *candidacy* for eviction; the archive pointer decides
*permission*. A blob with no pointer is reported as
`skipped:no_archive_pointer` and left alone, even if it's the oldest,
least-used thing on disk. This is the direct implementation of the
project's own standing rule: never silently lose data, never claim
success that didn't happen.

## 4. The action ledger doubles as the storage manifest

Every consequential action — download, upload, external call, approval —
writes one append-only row: `actor`, `stage` (KNOW → THINK → PREPARE →
APPROVE → ACT → VERIFY → REMEMBER), `action`, a JSON `detail`, and
optionally a `blob_hash`. Because the ledger references `blob_hash`
directly, `SELECT * FROM action_ledger WHERE blob_hash = ?` answers "why
do we have this file" for anything currently on disk or in the archive.
This is both your audit trail (already required by the project's
security rules) and free storage provenance — one table, two jobs.

## 5. Background jobs so storage work never blocks chat

Downloading a video, extracting a transcript, or embedding a document
are all I/O-heavy and sometimes slow on mobile data. None of that should
hold up a chat response. The job queue (`core/jobs.py`) is a single
SQLite table with atomic claim-and-run semantics and automatic retry up
to `max_attempts` — deliberately not a separate service, because on a
single phone, one more daemon to keep alive is a liability, not a
feature.

## 6. Budget enforcement

`enforce_storage_budget(max_hot_bytes, min_free_bytes)` walks hot blobs
oldest-accessed-first and evicts (per the rule in §3) until under budget
or out of eligible candidates — whichever comes first. If it can't reach
budget without touching un-archived blobs, it says so
(`still_over_budget: true`) instead of pretending the problem is solved.
Run this on a schedule (e.g. once a day, or before any large new
ingest) rather than only reactively.

## 7. What this spec deliberately does not do

- It does not implement a Telegram (or any) uploader. `register_archive_ref`
  only records that an upload already happened elsewhere — wire the
  actual upload call in wherever your archive provider client lives.
- It does not change any existing table, route, or behavior in the v0.6
  build. Everything here is additive.
- It does not introduce a new external dependency or service (no Redis,
  no Celery, no S3 SDK) — everything is stdlib + the existing SQLite file,
  by design, for a Termux deployment.
