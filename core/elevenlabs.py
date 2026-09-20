"""ElevenLabs text-to-speech client.

Stdlib-only (no new dependency), matching core/brave.py's style. Never
fabricates audio: if ELEVENLABS_API_KEY is unset or the API call fails,
callers get a clear exception/None rather than silent fake success.
"""
import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE_URL = "https://api.elevenlabs.io/v1"


def _key() -> str:
    return os.getenv("ELEVENLABS_API_KEY", "").strip()


def configured() -> bool:
    return bool(_key())


def default_voice_id() -> str:
    # A voice ID must be supplied by ElevenLabs (voices are per-account/library).
    # No default voice is invented -- if unset, callers must pass one explicitly
    # or /status will report which env var is missing.
    return os.getenv("ELEVENLABS_VOICE_ID", "").strip()


def list_voices() -> list[dict]:
    key = _key()
    if not key:
        raise RuntimeError("ElevenLabs is not configured (ELEVENLABS_API_KEY unset)")
    req = Request(f"{BASE_URL}/voices", headers={"xi-api-key": key, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"ElevenLabs voices request failed: {exc}") from exc
    return [
        {"voice_id": v.get("voice_id", ""), "name": v.get("name", ""), "category": v.get("category", "")}
        for v in data.get("voices", [])
    ]


def synthesize(text: str, voice_id: str = "", model_id: str = "eleven_turbo_v2_5",
               stability: float = 0.5, similarity_boost: float = 0.75) -> bytes:
    """Returns raw MP3 bytes. Raises RuntimeError with a clear message on any failure."""
    key = _key()
    if not key:
        raise RuntimeError("ElevenLabs is not configured (ELEVENLABS_API_KEY unset)")
    voice = (voice_id or default_voice_id()).strip()
    if not voice:
        raise RuntimeError("No ElevenLabs voice_id given and ELEVENLABS_VOICE_ID is not set")
    text = (text or "").strip()
    if not text:
        raise RuntimeError("Empty text")
    if len(text) > 5000:
        text = text[:5000]

    payload = json.dumps({
        "text": text,
        "model_id": model_id,
        "voice_settings": {"stability": stability, "similarity_boost": similarity_boost},
    }).encode("utf-8")

    req = Request(
        f"{BASE_URL}/text-to-speech/{voice}",
        data=payload,
        headers={
            "xi-api-key": key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=45) as response:
            audio = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace") if exc.fp else str(exc)
        raise RuntimeError(f"ElevenLabs synthesis failed ({exc.code}): {detail[:300]}") from exc
    except URLError as exc:
        raise RuntimeError(f"ElevenLabs synthesis failed: {exc}") from exc
    if not audio:
        raise RuntimeError("ElevenLabs returned no audio")
    return audio
