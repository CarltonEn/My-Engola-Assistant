# Replit reconciliation — v0.21.0

Good engineerable capabilities recovered from the Replit project without replacing the router-split FastAPI architecture:

- public RSS current-news research with explicit source/publication provenance;
- secure HTTP response headers;
- PDF/TXT/Markdown multipart knowledge upload;
- upload-to-content-addressed-storage plus knowledge-vault registration;
- automatic archive-job handoff when an archive provider is configured;
- preservation of the existing YouTube, voice, knowledge, task, memory and companion capabilities already present in the reconciled FastAPI tree.

Rejected as a foundation: the Replit Flask/SQLite monolith, its duplicate schema, browser-only state model, and any capability that conflicts with the owner-authenticated router architecture.


## Deliberately not copied

The Flask monolith, its duplicate SQLite schema, inline-only request model, browser/localStorage persistence, and any claim that an external service is connected were not copied. Their useful behavior was re-expressed behind Engola's owner-gated FastAPI routers and shared storage/knowledge primitives.


## v0.22.0 verification pass

This release fixes the remaining issues found during live smoke testing: the
Knowledge Wiki route now precedes the dynamic source route; integration status
uses provider-namespaced state and includes archive providers; Google/GitHub
Connect controls refuse to navigate when OAuth is unconfigured; disconnect
actions accept POST as well as GET; the v0.18 live-status layer is served;
and FastAPI startup/shutdown now uses lifespan handlers.

Verified: 53 tests passing, all static JavaScript files pass `node --check`,
and the structural self-check passes. External provider credentials remain
intentionally unconfigured.
