# Engola Final v1.0 — Consolidated Installer

This is the final self-contained consolidation installer for the current Engola repository.

It is designed to be idempotent and safe against the earlier brittle `main.py` home-route failures. It patches the actual files in `~/Engola-master`, preserves a timestamped rollback backup, validates Python syntax, wires the consolidated Google/GitHub/research/executive routers, fixes natural task/memory commands, adds Gmail scope support, and points the existing v16 connection UI at the consolidated OAuth routes.

Run from `~/Engola-master`:

    python upgrade_engola_final.py

No API key or secret is embedded in this package.
