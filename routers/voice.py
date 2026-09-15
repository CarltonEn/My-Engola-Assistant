"""
Voice narration shaping.

Produces a paced narration script (sentence/paragraph segmentation, pause
durations, SSML <break> tags, estimated read time) in the "warm, deep,
measured British documentary-narration style" described in the SYSTEM
prompt -- WITHOUT synthesizing audio and WITHOUT imitating any specific
living narrator's voice.

This module never performs text-to-speech. If a TTS provider key is not
configured, /api/voice/narrate is explicit that only the shaped script is
returned, not audio -- consistent with "never claim an integration
succeeded unless it did."
"""
import os
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.security import require_owner

router = APIRouter(prefix="/api/voice", tags=["voice"])

_WORDS_PER_MINUTE = 130  # measured documentary pace, slower than conversational ~150-160wpm
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_SHORT_PAUSE_MS = 350   # between sentences
_LONG_PAUSE_MS = 850    # between paragraphs
_COMMA_PAUSE_MS = 150   # after commas/semicolons/colons within a long sentence


def _estimate_seconds(text: str) -> float:
    words = len(text.split())
    return round((words / _WORDS_PER_MINUTE) * 60, 2)


def shape_narration(text: str):
    """Returns (segments, ssml, total_seconds)."""
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    segments = []
    ssml_parts = ["<speak>"]
    total_seconds = 0.0

    for p_idx, paragraph in enumerate(paragraphs):
        sentences = [s.strip() for s in _SENTENCE_SPLIT.split(paragraph) if s.strip()]
        for s_idx, sentence in enumerate(sentences):
            is_last_in_paragraph = s_idx == len(sentences) - 1
            is_last_paragraph = p_idx == len(paragraphs) - 1
            pause_after_ms = 0
            if not (is_last_in_paragraph and is_last_paragraph):
                pause_after_ms = _LONG_PAUSE_MS if is_last_in_paragraph else _SHORT_PAUSE_MS
            seconds = _estimate_seconds(sentence)
            total_seconds += seconds
            segments.append(
                {
                    "text": sentence,
                    "paragraph_index": p_idx,
                    "estimated_seconds": seconds,
                    "pause_after_ms": pause_after_ms,
                }
            )
            ssml_sentence = re.sub(r"([,;:])", r"\1<break time='%dms'/>" % _COMMA_PAUSE_MS, sentence)
            ssml_parts.append(f"<s>{ssml_sentence}</s>")
            if pause_after_ms:
                ssml_parts.append(f"<break time='{pause_after_ms}ms'/>")

    ssml_parts.append("</speak>")
    return segments, "".join(ssml_parts), round(total_seconds, 2)


@router.post("/narrate")
async def narrate(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "text is required."}, status_code=400)

    segments, ssml, total_seconds = shape_narration(text)
    tts_configured = bool(os.getenv("TTS_PROVIDER_API_KEY", "").strip())

    return {
        "segments": segments,
        "ssml": ssml,
        "estimated_seconds": total_seconds,
        "audio_url": None,
        "tts_configured": tts_configured,
        "note": (
            "This is a paced narration script only; no audio was synthesized."
            if not tts_configured
            else "TTS_PROVIDER_API_KEY is set, but no audio synthesis integration is wired up yet; "
            "only the paced script is returned."
        ),
    }
