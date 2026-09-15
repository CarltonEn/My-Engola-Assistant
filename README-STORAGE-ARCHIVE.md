# Engola 0.11.0 — Storage + Archive Provider Layer

This build turns the storage kit's archive-pointer design into a real provider
pipeline.

## Data flow

1. Incoming bytes are SHA-256 addressed and deduplicated locally.
2. The upload endpoint queues an `archive_blob` job when one or more archive
   providers are configured.
3. The worker uploads the bytes to each configured provider.
4. A provider pointer is recorded only after a successful provider response.
5. The action ledger records PREPARE → ACT → VERIFY for the archive operation.
6. Hot-tier eviction/budget enforcement is permitted only when at least one
   verified archive pointer exists.
7. A cold blob can be restored through the same provider abstraction; the bytes
   are SHA-256 verified before being rehydrated locally.

## Provider configuration

`ENGOLA_ARCHIVE_PROVIDERS` is a comma-separated list. Current providers:

- `telegram` — private Telegram archive chat/channel via Bot API.
- `gmail` — connected Google mailbox via Gmail API; intended for smaller files
  because email attachment/message limits apply.

Example:

```text
ENGOLA_ARCHIVE_PROVIDERS=telegram,gmail
ENGOLA_AUTO_ARCHIVE=1
ENGOLA_TELEGRAM_BOT_TOKEN=...
ENGOLA_TELEGRAM_ARCHIVE_CHAT_ID=...
```

No credentials are stored in source. Telegram credentials are read from the
runtime environment. Gmail uses the existing owner-only Google OAuth token
store and must be re-authorized when the Gmail scope is newly requested.

## API additions

- `GET /api/storage/providers`
- `GET /api/storage/blobs/{sha256}/archives`
- `POST /api/storage/blobs/{sha256}/archive`
- `POST /api/storage/blobs/{sha256}/restore`

Existing storage endpoints remain available.

## Adding providers

Implement the `ArchiveProvider` contract in `core/archive.py`, return an
`ArchivePointer` only after the external service confirms the upload, and add
the provider to `PROVIDERS`. The rest of Engola remains provider-agnostic.

This makes future Drive, S3-compatible, OneDrive, Dropbox or other durable
archives additive rather than requiring a rewrite of Engola storage.
