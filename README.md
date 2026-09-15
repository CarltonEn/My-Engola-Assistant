# Engola — Reconciled Platform Foundation

Engola is a private, owner-authenticated AI chief of staff.

Current reconciled foundation: **0.22.0 hardened**.

## Architecture

- FastAPI router-split backend
- WebAuthn/passkey owner authentication
- Local deterministic workspace operations
- Optional OpenAI and Gemini reasoning providers
- British-English voice output and browser microphone input
- Knowledge/media/career/Uganda intelligence layers
- Content-addressable Hot/Warm/Cold storage
- Pluggable Telegram/Gmail archive providers
- SQLite background job queue
- Outbound Termux/Linux/Windows-compatible agent bridge
- GitHub/Google OAuth capability layer
- Action/provenance model: KNOW → THINK → PREPARE → APPROVE → ACT → VERIFY → REMEMBER

## Truthfulness

A capability is not considered available because a button exists. Runtime state must show whether a provider is available, needs permission, is unavailable, or is not implemented.

Large originals are archived externally only after verified provider success. Local eviction is never allowed merely because a file is old.

## Development

Run the offline suite with:

```bash
pytest -q
```

Run the platform self-check with:

```bash
python tools/engola_selfcheck.py
```

See `RECONCILIATION.md` and `docs/reconciliation/` for the source-of-truth decision and the reviewed project materials.
