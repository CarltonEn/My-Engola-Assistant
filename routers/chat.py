import json
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core import ai
from core.agent import run_local
from core.config import SYSTEM_PROMPT
from core.db import db, memory_text, recent, save_message
from core.security import require_owner
from core.knowledge import search_for_chat
from core.gemini import configured as gemini_configured, respond as gemini_respond
from core.brave import configured as brave_configured, llm_context, answer as brave_answer
from core.persona import conversational, owner_snapshot


router = APIRouter(prefix="/api", tags=["chat"])


def _base_messages():
    prompt = (
        SYSTEM_PROMPT
        + "\n\nOwner profile:\n"
        + owner_snapshot()
        + "\n\nKnown owner memory:\n"
        + (memory_text() or "(none)")
    )

    messages = [
        {
            "role": "system",
            "content": prompt,
        }
    ]

    messages += [
        {"role": role, "content": content}
        for role, content in recent()
    ]

    return messages


def _brave_grounding(text: str) -> str:
    """Get web context from Brave without making it the final answer."""

    if not brave_configured():
        return ""

    try:
        data = llm_context(text, count=5)

        # Brave may return different context shapes as the API evolves.
        # Preserve useful text while avoiding dumping raw JSON into prompts.
        chunks = []

        for key in ("context", "results", "web"):
            value = data.get(key)

            if isinstance(value, str):
                chunks.append(value)

            elif isinstance(value, list):
                for item in value[:8]:
                    if isinstance(item, str):
                        chunks.append(item)
                    elif isinstance(item, dict):
                        title = item.get("title", "")
                        url = item.get("url", "")
                        description = (
                            item.get("description")
                            or item.get("snippet")
                            or item.get("content")
                            or ""
                        )

                        block = "\n".join(
                            x for x in (
                                f"TITLE: {title}" if title else "",
                                f"URL: {url}" if url else "",
                                description,
                            )
                            if x
                        )

                        if block:
                            chunks.append(block)

            elif isinstance(value, dict):
                chunks.append(json.dumps(value, ensure_ascii=False))

        if chunks:
            return "\n\n---\n\n".join(chunks)[:30000]

    except Exception:
        pass

    return ""


def _provider_answer(text: str, grounding: str = "") -> str:
    messages = _base_messages()

    if grounding:
        messages.append(
            {
                "role": "system",
                "content": (
                    "WEB GROUNDING FROM BRAVE SEARCH:\n\n"
                    + grounding
                    + "\n\nUse this evidence when relevant. "
                    "Do not invent facts that are not supported by the evidence "
                    "or your reliable knowledge."
                ),
            }
        )

    messages.append(
        {
            "role": "user",
            "content": text,
        }
    )

    return ai.respond(messages)


@router.post("/chat")
async def chat(request: Request):
    denied = require_owner(request)

    if denied:
        return denied

    try:
        body = await request.json()
        text = (body.get("message") or "").strip()

        if not text:
            return JSONResponse(
                {"ok": False, "error": "Empty message"},
                status_code=400,
            )

        save_message("user", text)

        # ---------------------------------------------------------
        # LOCAL AGENT
        # ---------------------------------------------------------

        local = run_local(text)

        if local.intent != "unhandled":
            save_message("assistant", local.answer)

            return {
                "ok": True,
                "answer": local.answer,
                "mode": "local",
                "intent": local.intent,
                "action": local.action,
                "executed": local.executed,
                "verified": local.verified,
                "needs_approval": local.needs_approval,
                "data": local.data,
            }

        # ---------------------------------------------------------
        # KNOWLEDGE VAULT
        # ---------------------------------------------------------

        try:
            evidence = search_for_chat(text, limit=4)
        except Exception:
            evidence = []

        # ---------------------------------------------------------
        # WEB GROUNDING
        # ---------------------------------------------------------

        grounding = _brave_grounding(text)

        if evidence:
            knowledge_blocks = []

            for item in evidence:
                knowledge_blocks.append(
                    f"SOURCE: {item.get('title') or item.get('url') or 'Stored source'}\n"
                    f"URL: {item.get('url') or ''}\n"
                    f"{item.get('excerpt') or ''}"
                )

            vault_context = "\n\n---\n\n".join(knowledge_blocks)

            grounding = (
                "KNOWLEDGE VAULT:\n"
                + vault_context
                + (
                    "\n\nWEB SEARCH:\n"
                    + grounding
                    if grounding
                    else ""
                )
            )

        # ---------------------------------------------------------
        # PRIMARY AI
        # ---------------------------------------------------------

        if ai.is_configured():
            try:
                answer = conversational(
                    _provider_answer(
                        text,
                        grounding=grounding,
                    )
                )

                save_message("assistant", answer)

                return {
                    "ok": True,
                    "answer": answer,
                    "mode": "provider",
                    "intent": "reasoning",
                    "executed": False,
                    "verified": True,
                    "needs_approval": False,
                    "data": {
                        "web_grounded": bool(grounding),
                        "knowledge_grounded": bool(evidence),
                    },
                }

            except Exception as e:
                # Continue to the next provider rather than killing the
                # conversation when the primary model is unavailable.
                primary_error = (
                    f"{type(e).__name__}: {e}"
                )
        else:
            primary_error = "OpenAI provider is not configured"

        # ---------------------------------------------------------
        # GEMINI
        # ---------------------------------------------------------

        if gemini_configured():
            try:
                messages = _base_messages()

                if grounding:
                    messages.append(
                        {
                            "role": "system",
                            "content": (
                                "Relevant grounding:\n\n"
                                + grounding
                            ),
                        }
                    )

                messages.append(
                    {
                        "role": "user",
                        "content": text,
                    }
                )

                answer = conversational(
                    gemini_respond(messages)
                )

                save_message("assistant", answer)

                return {
                    "ok": True,
                    "answer": answer,
                    "mode": "gemini",
                    "intent": "reasoning",
                    "executed": False,
                    "verified": True,
                    "needs_approval": False,
                    "data": {
                        "web_grounded": bool(grounding),
                        "knowledge_grounded": bool(evidence),
                    },
                }

            except Exception as e:
                gemini_error = f"{type(e).__name__}: {e}"
        else:
            gemini_error = "Gemini provider is not configured"

        # ---------------------------------------------------------
        # BRAVE AI-GROUNDED FALLBACK
        # ---------------------------------------------------------

        if brave_configured():
            try:
                messages = _base_messages()

                messages.append(
                    {
                        "role": "user",
                        "content": text,
                    }
                )

                answer = conversational(
                    brave_answer(messages)
                )

                save_message("assistant", answer)

                return {
                    "ok": True,
                    "answer": answer,
                    "mode": "brave",
                    "intent": "web_reasoning",
                    "executed": False,
                    "verified": True,
                    "needs_approval": False,
                    "data": {
                        "web_grounded": True,
                    },
                }

            except Exception as e:
                brave_error = f"{type(e).__name__}: {e}"
        else:
            brave_error = "Brave Search is not configured"

        # ---------------------------------------------------------
        # KNOWLEDGE-ONLY FALLBACK
        # ---------------------------------------------------------

        if evidence:
            blocks = []

            for item in evidence:
                blocks.append(
                    f"SOURCE: {item.get('title') or item.get('url') or 'Stored source'}\n"
                    f"URL: {item.get('url') or ''}\n"
                    f"{item.get('excerpt') or ''}"
                )

            answer = (
                "I found relevant information in your Knowledge Vault, Sir.\n\n"
                + "\n\n---\n\n".join(blocks)
            )

            save_message("assistant", answer)

            return {
                "ok": True,
                "answer": answer,
                "mode": "knowledge",
                "intent": "knowledge_lookup",
                "action": "search_knowledge_vault",
                "executed": True,
                "verified": True,
                "needs_approval": False,
                "data": {"sources": evidence},
            }

        # ---------------------------------------------------------
        # HONEST FINAL FALLBACK
        # ---------------------------------------------------------

        answer = (
            "I don't have a connected reasoning provider available right now, Sir."
        )

        save_message("assistant", answer)

        return {
            "ok": True,
            "answer": answer,
            "mode": "local",
            "intent": "unhandled",
            "executed": False,
            "verified": False,
            "needs_approval": False,
            "data": {
                "providers": {
                    "openai": ai.is_configured(),
                    "gemini": gemini_configured(),
                    "brave": brave_configured(),
                },
                "errors": {
                    "openai": primary_error,
                    "gemini": gemini_error,
                    "brave": brave_error,
                },
            },
        }

    except Exception as e:
        return JSONResponse(
            {
                "ok": False,
                "error": (
                    "Engola chat execution failed: "
                    f"{type(e).__name__}: {e}"
                ),
            },
            status_code=500,
        )


@router.post("/clear")
def clear_chat(request: Request):
    denied = require_owner(request)

    if denied:
        return denied

    with db() as conn:
        conn.execute("DELETE FROM messages")
        conn.commit()

    return {"ok": True}


@router.get("/history")
def history(request: Request):
    denied = require_owner(request)

    if denied:
        return denied

    with db() as conn:
        rows = conn.execute(
            "SELECT role, content, ts FROM messages ORDER BY id ASC"
        ).fetchall()

        memories = conn.execute(
            "SELECT id, key, value, ts FROM memories ORDER BY id DESC"
        ).fetchall()

        permissions = conn.execute(
            """
            SELECT name, status, scope, updated_at
            FROM permissions
            ORDER BY name ASC
            """
        ).fetchall()

    return {
        "ok": True,
        "messages": [
            {
                "role": r[0],
                "content": r[1],
                "ts": r[2],
            }
            for r in rows
        ],
        "memories": [
            {
                "id": r[0],
                "key": r[1],
                "value": r[2],
                "ts": r[3],
            }
            for r in memories
        ],
        "permissions": [
            {
                "name": r[0],
                "status": r[1],
                "scope": r[2],
                "updated_at": r[3],
            }
            for r in permissions
        ],
    }
