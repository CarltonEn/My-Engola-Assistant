# Legacy compatibility notes

- `main.py` is the reconciled application entrypoint. Docker already launches `main:app`.
- Root `app.py` is retained only as historical compatibility/reference material from the earlier single-file lineage; it is not the source of truth.
- `routers/google_oauth.py` and `routers/github_oauth.py` are retained for backward compatibility. New UI connection flows use the consolidated `/api/integrations/...` routes from the final-consolidation material.
- The old v0.11/v0.13 patch directories are not included in this release package. Their useful capabilities were selectively reconciled into the main tree.
