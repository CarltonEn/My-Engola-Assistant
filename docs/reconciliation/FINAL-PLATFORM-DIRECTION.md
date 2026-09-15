# Engola final-platform direction

This build hardens the platform around one reusable control-plane protocol.

## Runtime model

**Owner → Engola → capability/approval gate → command queue → paired agent → execution → verification → audit**

Termux is the first worker. Linux and Windows workers use the same protocol.

## Security model

- Owner routes require the existing WebAuthn/session layer.
- Device routes require a paired device token.
- The server never opens an inbound listener on the worker.
- Executable jobs require explicit approval.
- Jobs expire.
- Claimed jobs have a short lease and are automatically re-queued if a worker disappears.
- Results are bounded before persistence.
- Idempotency keys prevent accidental duplicate queueing.
- Financial and career-submission permissions remain separate.

## Supported worker jobs

- `shell`
- `download`
- `telegram_upload`

The worker must never treat arbitrary server data as an instruction unless the
server has marked the job approved.

## Telegram archive

The worker streams files to Telegram rather than loading a whole archive file
into memory. The standard Bot API limit used here is 49 MB to leave margin.

## PC readiness

The worker uses Python standard-library primitives and platform-neutral HTTP,
subprocess and filesystem operations. A Windows/Linux agent can therefore use
the same pairing and command protocol without changing the server architecture.

## Operational goal

The web UI is a control surface, not the source of truth. Real state lives in
the database, agent jobs, integrations and knowledge vault.
