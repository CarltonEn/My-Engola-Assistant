from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse

from core import ai
from core.agent import run_local
from core.config import SYSTEM_PROMPT
from core.db import db, memory_text, recent, save_message
from core.security import require_owner
from core.knowledge import search_for_chat
from core.gemini import configured as gemini_configured, respond as gemini_respond
from core.persona import conversational, owner_snapshot

router = APIRouter(prefix="/api", tags=["chat"])

def _provider_answer(text: str) -> str:
    prompt = SYSTEM_PROMPT + "\n\nOwner profile:\n" + owner_snapshot() + "\n\nKnown owner memory:\n" + (memory_text() or "(none)")
    msgs = [{"role": "system", "content": prompt}]
    msgs += [{"role": role, "content": content} for role, content in recent()]
    msgs.append({"role": "user", "content": text})
    return ai.respond(msgs)

@router.post("/chat")
async def chat(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    try:
        body = await request.json()
        text = (body.get("message") or "").strip()
        if not text:
            return JSONResponse({"ok": False, "error": "Empty message"}, status_code=400)

        save_message("user", text)
        local = run_local(text)

        if local.intent != "unhandled":
            save_message("assistant", local.answer)
            return {
                "ok": True, "answer": local.answer, "mode": "local",
                "intent": local.intent, "action": local.action,
                "executed": local.executed, "verified": local.verified,
                "needs_approval": local.needs_approval, "data": local.data,
            }

        try:
            evidence = search_for_chat(text, limit=4)
        except Exception:
            evidence = []

        if evidence and not ai.is_configured():
            blocks = []
            for item in evidence:
                blocks.append(
                    f"SOURCE: {item.get('title') or item.get('url') or 'Stored source'}\n"
                    f"URL: {item.get('url') or ''}\n{item.get('excerpt') or ''}"
                )
            answer = (
                "I found this in your Knowledge Vault, Sir.\n\n"
                + "\n\n---\n\n".join(blocks)
            )
            save_message("assistant", answer)
            return {"ok": True, "answer": answer, "mode": "knowledge",
                    "intent": "knowledge_lookup", "action": "search_knowledge_vault",
                    "executed": True, "verified": True, "needs_approval": False,
                    "data": {"sources": evidence}}

        if ai.is_configured():
            try:
                answer = conversational(_provider_answer(text))
            except Exception as e:
                return JSONResponse({"ok": False, "error": f"AI request failed: {type(e).__name__}: {e}"}, status_code=502)
            save_message("assistant", answer)
            return {"ok": True, "answer": answer, "mode": "provider",
                    "intent": "reasoning", "executed": False,
                    "verified": True, "needs_approval": False}

        if gemini_configured():
            try:
                msgs = [{"role": "system", "content": SYSTEM_PROMPT + "\n\nOwner profile:\n" + owner_snapshot() + "\n\nKnown owner memory:\n" + (memory_text() or "(none)")}]
                msgs += [{"role": role, "content": content} for role, content in recent()]
                if evidence:
                    msgs.append({"role": "system", "content": "Relevant Knowledge Vault evidence:\n" + "\n\n".join(str(x) for x in evidence)})
                msgs.append({"role": "user", "content": text})
                answer = conversational(gemini_respond(msgs))
            except Exception as e:
                return JSONResponse({"ok": False, "error": f"Reasoning provider failed: {type(e).__name__}: {e}"}, status_code=502)
            save_message("assistant", answer)
            return {"ok": True, "answer": answer, "mode": "gemini",
                    "intent": "reasoning", "executed": False,
                    "verified": True, "needs_approval": False}

        save_message("assistant", local.answer)
        return {"ok": True, "answer": local.answer, "mode": "local",
                "intent": local.intent, "executed": False,
                "verified": False, "needs_approval": False}
    except Exception as e:
        return JSONResponse(
            {"ok": False, "error": f"Engola chat execution failed: {type(e).__name__}: {e}"},
            status_code=500,
        )

@router.post("/clear")
def clear_chat(request: Request):
    denied = require_owner(request)
    if denied: return denied
    with db() as conn:
        conn.execute("DELETE FROM messages")
        conn.commit()
    return {"ok": True}

@router.get("/history")
def history(request: Request):
    denied = require_owner(request)
    if denied: return denied
    with db() as conn:
        rows = conn.execute("SELECT role, content, ts FROM messages ORDER BY id ASC").fetchall()
        memories = conn.execute("SELECT id, key, value, ts FROM memories ORDER BY id DESC").fetchall()
        permissions = conn.execute("SELECT name, status, scope, updated_at FROM permissions ORDER BY name ASC").fetchall()
    return {
        "ok": True,
        "messages": [{"role": r[0], "content": r[1], "ts": r[2]} for r in rows],
        "memories": [{"id": r[0], "key": r[1], "value": r[2], "ts": r[3]} for r in memories],
        "permissions": [{"name": r[0], "status": r[1], "scope": r[2], "updated_at": r[3]} for r in permissions],
    }
