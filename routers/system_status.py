import os

from fastapi import APIRouter, Request

from core.ai import is_configured as openai_configured
from core.command_bridge import recent
from core.db import db
from core.gemini import configured as gemini_configured
from core.security import require_owner

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status")
def status(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    with db() as conn:
        knowledge = conn.execute("SELECT COUNT(*) FROM knowledge_sources").fetchone()[0] if _table(conn, "knowledge_sources") else 0
        devices = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0] if _table(conn, "devices") else 0
        tasks = conn.execute("SELECT COUNT(*) FROM tasks WHERE status != 'done'").fetchone()[0] if _table(conn, "tasks") else 0
        projects = conn.execute("SELECT COUNT(*) FROM projects WHERE status != 'done'").fetchone()[0] if _table(conn, "projects") else 0
        decisions = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] if _table(conn, "decisions") else 0
        reminders = conn.execute("SELECT COUNT(*) FROM reminders WHERE status = 'pending'").fetchone()[0] if _table(conn, "reminders") else 0
    try:
        from routers.voice_natural import DEFAULT_VOICE
        voice = {"available": _voice_available(), "voice": DEFAULT_VOICE, "locale": "en-GB"}
    except Exception:
        voice = {"available": False, "voice": None, "locale": "en-GB"}
    return {
        "ok": True,
        "providers": {"openai": openai_configured(), "gemini": gemini_configured()},
        "voice": voice,
        "knowledge_sources": knowledge,
        "paired_devices": devices,
        "open_tasks": tasks,
        "active_projects": projects,
        "decisions": decisions,
        "pending_reminders": reminders,
        "queued_commands": len([x for x in recent(20) if x["status"] in ("queued", "claimed")]),
        "telegram_archive_configured": bool(os.getenv("ENGOLA_TELEGRAM_BOT_TOKEN") and os.getenv("ENGOLA_TELEGRAM_ARCHIVE_CHAT_ID")),
    }


def _table(conn, name: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def _voice_available() -> bool:
    try:
        import edge_tts  # noqa: F401
        return True
    except Exception:
        return False
