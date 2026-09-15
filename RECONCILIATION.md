# Engola — Master Reconciliation

Status: reconciled engineering foundation
Date: 2026-09-14

## Source-of-truth decision

The project contains multiple historical branches, patches and mockups. They are not merged by filename/version number. The authoritative implementation direction is:

1. `Engola-current.zip` / router-split FastAPI architecture as the real application baseline.
2. `Engola-v0.10.1-mic-input.zip` as the verified microphone-input continuation.
3. `Engola-v0.11.0-storage-archive.zip` as the storage/archive implementation foundation.
4. v0.11–v0.19 historical patches as feature specifications and source material, reconciled selectively rather than blindly overlaid.
5. `engola-storage-kit.zip` as the storage invariants: SHA-256 identity, Hot/Warm/Cold tiers, archive-proof eviction, action ledger and SQLite jobs.
6. Stitch/Magic Patterns UI as UX/information-architecture reference only. Its localStorage/mock backend is not merged as production persistence.
7. `ENGOLA-AGENT-BRIEFING.md` and the Critical Implementation Brief govern security, release discipline and capability truthfulness.

## Reconciled capabilities

- Owner WebAuthn/passkey authentication remains authoritative.
- Setup authorization is not a normal login and recovery must remain a separate future/next hardening item unless explicitly implemented and tested.
- Local command layer remains available without a paid AI provider.
- OpenAI is optional; Gemini is optional; provider failure is explicit.
- Browser microphone input and British-English voice output remain part of Assistant.
- Knowledge, Media, Tasks, Memory and Capabilities remain the core workspace model.
- Career and Uganda knowledge remain real functional domains.
- Knowledge provenance and six authority tiers remain first-class.
- YouTube analysis is labeled by transcript/caption/metadata basis and never claims audiovisual viewing without evidence.
- Storage is content-addressed by SHA-256 and uses Hot/Warm/Cold lifecycle rules.
- Telegram and Gmail are pluggable archive providers; credentials are runtime-only.
- Background archive/restore work is queued rather than blocking chat.
- Device/Termux is an outbound worker using the command bridge; v0.19 lease/idempotency hardening is retained.
- GitHub OAuth is a capability connection, not an unconditional claim of repository control.
- The action lifecycle remains KNOW → THINK → PREPARE → APPROVE → ACT → VERIFY → REMEMBER.
- Magic Patterns' Assistant-first split workspace is the UX reference; it must be wired to real FastAPI state rather than localStorage mocks.

## Storage/archive contract

`core/storage.py` owns bytes and content identity. `core/archive.py` owns provider abstraction. A provider returns an archive pointer only after confirmed upload. Local eviction is permitted only when a verified archive pointer exists. Restore verifies SHA-256 before rehydration.

Telegram is the preferred first cold archive. Gmail is a secondary archive/replica for smaller files. Future Drive/S3/OneDrive/Dropbox adapters implement the same provider contract without changing the storage engine.

## Integration/token policy

No integration token is required to keep building the architecture. When an integration becomes the next real feature, request only the minimum credential/scope needed, keep it server/Termux-side, and guide the owner through obtaining it. Never put tokens in source, frontend code, tests, screenshots or chat logs.

Planned provider families include Google/Gmail/Calendar, GitHub, Telegram, object storage, and other services as justified by a real capability. Each must report one of: available, needs permission, unavailable, or not implemented.

## UI reconciliation

The Magic Patterns layout is reconciled conceptually as:

`Assistant` = primary conversation/voice surface.

`Workspace` = Knowledge / Media / Tasks / Memory / Capabilities.

`Command Center` = operational work: background jobs, approvals, device status, storage status and action history; it is not a fake analytics dashboard.

Desktop uses Assistant + workspace side rail. Mobile uses Assistant-first stacked layout with a collapsible Work/More surface.

## Deliberate non-goals

- No fake metrics.
- No fake integrations.
- No client-side secrets.
- No silent permissions.
- No automatic irreversible actions.
- No replacement of the real FastAPI backend with the Stitch mock backend.
- No claim that Telegram/Gmail is connected until runtime credentials/OAuth are actually configured and tested.

## v1.0 consolidation material

`Engola-FINAL-v1.0-consolidation-FIXED2` is treated as an additional consolidation source, not as an unconditional installer. Its provider-neutral Google/GitHub clients, consolidated integration routes, research route and executive overview have been incorporated where compatible with the router-split architecture. Its legacy assumptions about static assets and versioning are not allowed to overwrite the newer reconciled baseline.

## Release status / remaining engineering work

This reconciliation build is an integration foundation, not a claim that every historical feature is production-complete. In particular, external credentials are intentionally unconfigured until the owner authorizes each provider; Telegram/Gmail uploads require real runtime authorization and end-to-end provider tests; the Magic Patterns visual concept remains a UX reference that still needs a deliberate wiring pass into the real static frontend; and semantic/vector retrieval plus the full external tool/function-calling loop remain future intelligence-layer work. Historical features that conflict with the verified router-split/security architecture are not copied merely because an older ZIP called itself final.
