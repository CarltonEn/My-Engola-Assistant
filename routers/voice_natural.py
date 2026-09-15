"""Natural British neural voice for Engola.

Primary: Microsoft Edge neural TTS via edge-tts (no API key).
Fallback remains the browser speech engine if synthesis is unavailable.
"""
import asyncio
import io
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from core.security import require_owner

router = APIRouter(prefix="/api/voice", tags=["voice"])

DEFAULT_VOICE = os.getenv("ENGOLA_TTS_VOICE", "en-GB-RyanNeural")
DEFAULT_RATE = os.getenv("ENGOLA_TTS_RATE", "-4%")
DEFAULT_PITCH = os.getenv("ENGOLA_TTS_PITCH", "-2Hz")


def _synth(text: str, voice: str, rate: str, pitch: str) -> bytes:
    import edge_tts

    async def run():
        communicate = edge_tts.Communicate(
            text,
            voice=voice,
            rate=rate,
            pitch=pitch,
        )
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        return buf.getvalue()

    return asyncio.run(run())


@router.get("/status")
def status(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    try:
        import edge_tts  # noqa: F401
        available = True
    except Exception:
        available = False
    return {
        "ok": True,
        "available": available,
        "provider": "edge-neural",
        "voice": DEFAULT_VOICE,
        "locale": "en-GB",
        "rate": DEFAULT_RATE,
        "pitch": DEFAULT_PITCH,
    }


@router.post("/speak")
async def speak(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"ok": False, "error": "Empty text"}, status_code=400)
    if len(text) > 5000:
        text = text[:5000]
    voice = (body.get("voice") or DEFAULT_VOICE).strip()
    rate = (body.get("rate") or DEFAULT_RATE).strip()
    pitch = (body.get("pitch") or DEFAULT_PITCH).strip()
    try:
        audio = await asyncio.to_thread(_synth, text, voice, rate, pitch)
        if not audio:
            raise RuntimeError("No audio received")
        return StreamingResponse(
            io.BytesIO(audio),
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-store", "X-Engola-Voice": voice},
        )
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "error": f"Voice synthesis unavailable: {type(exc).__name__}: {exc}"},
            status_code=503,
        )
