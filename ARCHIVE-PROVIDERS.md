# Engola Archive Providers

Engola now treats external storage as a provider layer. The local store remains
content-addressed by SHA-256; archive providers hold durable copies and return
verified pointers before local eviction is permitted.

## Telegram (recommended first cold archive)

Set:

```text
ENGOLA_ARCHIVE_PROVIDERS=telegram
ENGOLA_AUTO_ARCHIVE=1
ENGOLA_TELEGRAM_BOT_TOKEN=<real bot token>
ENGOLA_TELEGRAM_ARCHIVE_CHAT_ID=<private archive chat/channel id>
```

Create a private archive chat/channel, add the bot with permission to send
files, and use that chat as the archive destination. Engola uploads through the
Telegram Bot API in a background job. The returned message/document identifiers
are stored against the blob's SHA-256. Local eviction is refused until that
pointer exists.

## Gmail

Gmail is supported as an additional archive provider for smaller files. It
uses the existing Google OAuth account and sends the blob as an email to the
connected mailbox. Because email attachment/message limits are materially
smaller than Telegram/object storage, Gmail should be treated as a secondary
archive/replica, not the unlimited store.

Enable the Gmail scope by setting/reviewing `GOOGLE_SCOPES` and reconnecting the
Google account so consent is refreshed. Then:

```text
ENGOLA_ARCHIVE_PROVIDERS=telegram,gmail
```

## Adding more providers

Implement the `ArchiveProvider` interface in `core/archive.py` (or split
providers into `core/archive_providers/`), return an `ArchivePointer` only
after successful upload, and register the provider in `PROVIDERS`.

The rest of Engola does not need to know whether the cold bytes live in
Telegram, Gmail, Drive, S3, OneDrive, or another durable service.
