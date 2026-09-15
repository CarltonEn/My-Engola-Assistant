from fastapi import APIRouter, Request
from core.db import db
from core.security import require_owner

router = APIRouter(prefix="/api/preferences", tags=["preferences"])

_ALLOWED = {
    "accent": {"default", "silver", "blue", "green", "amber", "violet"},
    "appearance": {"system", "light", "dark"},
    "blur": {"on", "off"},
    "density": {"comfortable", "compact"},
    "voice": {"on", "off"},
    "voice_auto": {"on", "off"},
    "voice_locale": {"en-GB"},
    "voice_rate": {"0.85", "0.95", "1.0", "1.1"},
}

def _ensure():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS preferences (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL
        )""")

@router.get("")
def get_preferences(request: Request):
    denied = require_owner(request)
    if denied: return denied
    _ensure()
    with db() as conn:
        rows = conn.execute("SELECT key,value FROM preferences ORDER BY key").fetchall()
    data = {r[0]: r[1] for r in rows}
    data.setdefault("accent", "default")
    data.setdefault("appearance", "system")
    data.setdefault("blur", "on")
    data.setdefault("density", "comfortable")
    data.setdefault("voice", "on")
    data.setdefault("voice_auto", "off")
    data.setdefault("voice_locale", "en-GB")
    data.setdefault("voice_rate", "0.95")
    return {"ok": True, "preferences": data}

@router.post("")
async def set_preferences(request: Request):
    denied = require_owner(request)
    if denied: return denied
    _ensure()
    body = await request.json()
    changes = {}
    import time
    with db() as conn:
        for key, value in body.items():
            if key not in _ALLOWED or str(value) not in _ALLOWED[key]:
                continue
            value = str(value)
            conn.execute(
                "INSERT INTO preferences(key,value,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                (key, value, time.time())
            )
            changes[key] = value
    return {"ok": True, "updated": changes}
