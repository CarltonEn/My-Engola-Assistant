# Engola — Critical Implementation Brief
Date: 2026-09-11

## Ground truth verified against GitHub

Repository: CarltonEn/Engola-
Canonical production baseline: master @ 2c6555b63b7b4451126da109f95e234ee1f30e0c
Functional branch: v0.7-functional-core @ b3efe3756c9fda7a2cd3e37f622f935d12c30188

Important correction:
The v0.7-functional-core branch DOES exist on GitHub and is exactly one commit ahead of master. Do not delete it or recreate it.

The v0.7 commit adds:
- persistent Work task CRUD
- Memory GET/DELETE
- functional Work/Intelligence/Memory/Security UI changes
- honest Files/Automations states
- chat billing-error presentation

## Critical findings

1. Chat is not actually provider-independent.
   /api/chat requires OPENAI_API_KEY and calls the OpenAI Responses API.
   A configured key with inactive billing still produces a provider failure.
   Therefore the dashboard can look alive while the main assistant remains unusable.

2. Existing WebAuthn recovery is intentionally NOT a setup-token login.
   ENGOLA_SETUP_TOKEN is setup authorization used only when no owner credential exists.
   Do not turn it into a permanent login or general session bypass.

3. The previously proposed v0.7.1 recovery patch must NOT be applied.
   It incorrectly targeted assumptions about the baseline and would have created a standing setup-token login path.

4. The repository contains v0.7-functional-core. Work from that branch's code when building the next functional release; do not assume it is absent.

## Required next release: v0.8 Functional Core + Safe Recovery

### A. Authentication recovery

Implement a separate environment variable:
ENGOLA_RECOVERY_TOKEN

Rules:
- Never use ENGOLA_SETUP_TOKEN for owner login after an owner exists.
- Recovery token is only accepted by a dedicated recovery endpoint.
- Recovery token must be hashed before persistence.
- Recovery grant must expire quickly (10 minutes maximum).
- Recovery grant is single-use.
- Rate-limit recovery attempts.
- Recovery grant may ONLY authorize registration of a new WebAuthn credential.
- Recovery state must not authorize /api/chat, /api/work, /api/memory, /api/permissions, or other owner APIs.
- Successful registration consumes the recovery grant permanently.
- Then create a normal owner session.
- Existing owner credentials remain untouched.
- Add an audit record for recovery start, failed attempts, successful registration, and consumption.
- Do not store biometric data.

Recommended endpoints:
POST /api/auth/recovery/start
POST /api/auth/recovery/register/options
POST /api/auth/recovery/register/verify

Use a separate recovery cookie/session namespace from engola_session.

### B. Make Engola useful WITHOUT OpenAI billing

Do NOT fake AI answers.

Add a deterministic local command layer before the OpenAI provider. It should handle useful non-AI operations such as:
- health/status
- current stored tasks
- create/update/delete tasks
- list/delete memories
- permission status
- clear chat history
- help/capability discovery

For unsupported natural-language questions, return an explicit message such as:
"AI provider unavailable: OpenAI billing is not active. I can still operate your local Engola workspace and its stored tools."

The UI must distinguish:
LOCAL / WORKSPACE CAPABILITIES
from
AI PROVIDER UNAVAILABLE

When OpenAI becomes available, normal AI chat should work without changing the UI.

### C. Eliminate dead dashboard controls

Every sidebar/topbar/quick-action control must do one of:
1. perform a real operation,
2. open a real functional panel,
3. show a truthful unavailable/permission-required state.

No decorative buttons that silently do nothing.

For each panel, test the full click -> request -> response -> UI update path.

Minimum functional panels:
- Chat
- Work
- Memory
- Intelligence
- Security / Permissions
- Files (truthful local/connected-state UI)
- Automations (truthful scheduled-action UI)
- Media
- Career
- Uganda Knowledge
- Voice

### D. Tests

Add tests for:
- recovery token cannot call normal owner APIs
- recovery token expires
- recovery token is single-use
- recovery success registers a new credential
- old credential remains valid
- normal owner session is created only after successful WebAuthn registration
- rate limiting
- chat local-command path works without OPENAI_API_KEY
- unsupported chat returns an honest provider-unavailable response
- every functional panel's API route exists
- task CRUD
- memory GET/DELETE
- permissions GET/POST

Do not call a feature "functional" merely because its route imports successfully. Test the actual request/response behavior.

## Release discipline

Start from:
v0.7-functional-core @ b3efe3756c9fda7a2cd3e37f622f935d12c30188

Do NOT:
- modify production credentials in source
- expose any token in code, logs, README, tests, or frontend
- turn setup authorization into a standing login
- delete owner credentials/database as a shortcut
- claim OpenAI chat works while billing is inactive
- create fake/mock assistant answers that look real
- push or merge anything until tests and a manual browser smoke test pass

Before release:
- py_compile
- full offline test suite
- inspect git diff
- secret scan
- verify /health version
- verify auth status
- manually exercise every dashboard button
- verify chat local commands without OpenAI
- verify recovery flow in a clean browser profile
