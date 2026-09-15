# Engola UI Concept

A local, runnable redesign concept for Engola: a composed personal intelligence interface and a command-center dashboard. It was created from the repository's stated Jarvis-inspired direction; all assistant content is representative UI copy.

## What is included

- `frontend/index.html` — responsive, accessible interactive UI with Assistant, Command center, and Memory modes.
- `backend/app.py` — small FastAPI service with health, briefing, and conversation endpoints; it serves the UI at `/`.

## Run locally

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app:app --reload
```

Open `http://127.0.0.1:8000`.

## Integration notes

The frontend currently simulates requests so it can be reviewed without a running API. Replace the `send()` function in `frontend/index.html` with a call to `POST /api/converse` when connecting a real assistant model. The route shapes in `backend/app.py` are intentionally small and can be wired to your auth, vector memory, calendar, and model providers.
