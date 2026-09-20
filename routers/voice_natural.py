"""Natural voice for Engola.

Primary (if configured): ElevenLabs, via ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID.
Fallback: Microsoft Edge neural TTS via edge-tts (no API key required).
Ultimate fallback: the browser's own speech engine, client-side, if neither works.
No provider is ever faked -- /status reports exactly which one is active.
"""
import asyncio
import io
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from core import elevenlabs
from core.security import require_owner

router = APIRouter(prefix="/api/voice", tags=["voice"])

DEFAULT_VOICE = os.getenv("ENGOLA_TTS_VOICE", "en-GB-RyanNeural")
DEFAULT_RATE = os.getenv("ENGOLA_TTS_RATE", "-4%")
DEFAULT_PITCH = os.getenv("ENGOLA_TTS_PITCH", "-2Hz")


def _synth_edge(text: str, voice: str, rate: str, pitch: str) -> bytes:
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
        edge_available = True
    except Exception:
        edge_available = False
    eleven_configured = elevenlabs.configured()
    eleven_voice_set = bool(elevenlabs.default_voice_id())
    active = "elevenlabs" if (eleven_configured and eleven_voice_set) else ("edge-neural" if edge_available else "none")
    return {
        "ok": True,
        "available": active != "none",
        "provider": active,
        "elevenlabs": {
            "configured": eleven_configured,
            "voice_id_set": eleven_voice_set,
        },
        "edge_neural": {
            "available": edge_available,
            "voice": DEFAULT_VOICE,
            "locale": "en-GB",
            "rate": DEFAULT_RATE,
            "pitch": DEFAULT_PITCH,
        },
    }


@router.get("/elevenlabs/voices")
def elevenlabs_voices(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    if not elevenlabs.configured():
        return JSONResponse({"ok": False, "error": "ElevenLabs is not configured (ELEVENLABS_API_KEY unset)."}, status_code=503)
    try:
        voices = elevenlabs.list_voices()
        return {"ok": True, "voices": voices}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)


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

    provider = (body.get("provider") or "").strip().lower()  # "elevenlabs" | "edge" | "" (auto)
    use_elevenlabs = elevenlabs.configured() and elevenlabs.default_voice_id() and provider != "edge"

    if use_elevenlabs or provider == "elevenlabs":
        try:
            voice_id = (body.get("voice_id") or "").strip()
            audio = await asyncio.to_thread(elevenlabs.synthesize, text, voice_id)
            return StreamingResponse(
                io.BytesIO(audio),
                media_type="audio/mpeg",
                headers={"Cache-Control": "no-store", "X-Engola-Voice": "elevenlabs"},
            )
        except Exception as exc:
            if provider == "elevenlabs":
                # Caller explicitly asked for ElevenLabs -- report the real failure,
                # do not silently substitute a different voice.
                return JSONResponse({"ok": False, "error": f"ElevenLabs synthesis failed: {exc}"}, status_code=502)
            # Otherwise fall through to edge-tts below.

    voice = (body.get("voice") or DEFAULT_VOICE).strip()
    rate = (body.get("rate") or DEFAULT_RATE).strip()
    pitch = (body.get("pitch") or DEFAULT_PITCH).strip()
    try:
        audio = await asyncio.to_thread(_synth_edge, text, voice, rate, pitch)
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
