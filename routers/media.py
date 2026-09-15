"""
Media Intelligence router.

youtube_video_id / youtube_oembed are migrated unchanged from the v0.5
canonical app.py (watch/shorts/embed/youtu.be URL forms, invalid-input
returns None).

study_media is upgraded from a free-text summary into a structured
claims / facts / inference / uncertainty extraction, per
context/MEDIA-INTELLIGENCE-v0.5.md and the Study & Learn requirement. It
still never claims to have watched or listened to the video -- it is
honest that it works from the title/URL/note plus web search, and if the
model's structured JSON cannot be parsed, that failure is surfaced rather
than papered over with an invented structure.
"""
import hashlib
import json
import urllib.parse
import urllib.request

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core import ai
from core.config import SYSTEM_PROMPT
from core.db import remember, save_message
from core.knowledge import ingest_url
from core.security import origin, require_owner

router = APIRouter(prefix="/api/media", tags=["media"])


def youtube_video_id(url: str):
    try:
        u = urllib.parse.urlparse(url.strip())
        host = u.netloc.lower().split(":")[0]
        if host in {"youtu.be", "www.youtu.be"}:
            return u.path.strip("/").split("/")[0] or None
        if "youtube.com" in host:
            if u.path == "/watch":
                return urllib.parse.parse_qs(u.query).get("v", [None])[0]
            parts = u.path.strip("/").split("/")
            if len(parts) >= 2 and parts[0] in {"shorts", "embed"}:
                return parts[1]
    except Exception:
        pass
    return None


def youtube_oembed(video_id: str):
    try:
        target = "https://www.youtube.com/watch?v=" + video_id
        url = "https://www.youtube.com/oembed?url=" + urllib.parse.quote(target, safe="") + "&format=json"
        req = urllib.request.Request(url, headers={"User-Agent": "Engola/0.6"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return {}


@router.post("/youtube")
async def youtube_media(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    body = await request.json()
    url = (body.get("url") or "").strip()
    if not url:
        return JSONResponse({"error": "YouTube URL required."}, status_code=400)
    vid = youtube_video_id(url)
    if not vid:
        return JSONResponse({"error": "I could not identify a YouTube video from that URL."}, status_code=400)
    meta = youtube_oembed(vid)
    emb_origin = urllib.parse.quote(origin(request), safe="")
    return {
        "video_id": vid,
        "embed_url": f"https://www.youtube-nocookie.com/embed/{vid}?enablejsapi=1&origin={emb_origin}",
        "watch_url": f"https://www.youtube.com/watch?v={vid}",
        "title": meta.get("title", "YouTube video"),
        "author": meta.get("author_name", ""),
        "thumbnail": meta.get("thumbnail_url", ""),
    }


STUDY_INSTRUCTIONS = """Media item for private study:
Title: {title}
URL: {url}
Owner note: {note}

You have not watched or listened to this media and must not claim to have done so.
Use web search to verify the title/topic, identify authoritative related sources, and
extract useful public information about it.

Respond with ONLY a single JSON object (no markdown fences, no commentary) with exactly
these keys:
  "facts": array of strings - things you can verify from sources you found, each ideally
           with an inline (Source Name) reference.
  "claims": array of strings - notable claims the video/topic is reported to make, clearly
            attributed to "the video reportedly ..." rather than stated as your own facts.
  "inferences": array of strings - your own reasoning/connections drawn from the facts,
                clearly labeled as inference, not verified fact.
  "uncertainties": array of strings - things you could not verify or where sources conflict.
  "sources": array of strings - the concrete sources used (names/URLs).
  "connects_to_owner_knowledge": string - how this connects to what is already known about
                                  the owner from memory, or "" if nothing relevant.
If you cannot find enough information, return short/empty arrays rather than inventing content."""


def _parse_structured_study(raw: str):
    """Best-effort JSON parse. Returns (data, parse_error)."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
        expected = {"facts", "claims", "inferences", "uncertainties", "sources", "connects_to_owner_knowledge"}
        if not isinstance(data, dict) or not expected.issubset(data.keys()):
            return None, "Model response was valid JSON but missing expected fields."
        return data, None
    except Exception as e:
        return None, f"Could not parse structured response: {type(e).__name__}"


@router.post("/study")
async def study_media(request: Request):
    denied = require_owner(request)
    if denied:
        return denied
    body = await request.json()
    title = (body.get("title") or "").strip()
    url = (body.get("url") or "").strip()
    note = (body.get("note") or "").strip()
    if not url:
        return JSONResponse({"error": "Media URL required."}, status_code=400)
    if not ai.is_configured():
        # Free-first path: acquire the public page/video transcript into the vault.
        try:
            source = ingest_url(url)
            text = (source.get("text") or "").strip()
            excerpt = text[:12000]
            return {
                "mode": "free",
                "stored": True,
                "source": {k: source.get(k) for k in ("id", "url", "title", "kind", "status", "characters")},
                "excerpt": excerpt,
                "message": "I did not watch or listen to the media. I acquired the publicly available text/transcript and stored it for study."
            }
        except Exception as e:
            return JSONResponse({"error": f"Free media acquisition failed: {type(e).__name__}: {e}"}, status_code=502)

    prompt = STUDY_INSTRUCTIONS.format(title=title or "Unknown", url=url, note=note or "None")
    try:
        raw = ai.respond([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}])
    except Exception as e:
        return JSONResponse({"error": f"AI study request failed: {type(e).__name__}: {e}"}, status_code=502)

    structured, parse_error = _parse_structured_study(raw)
    label = title or url
    if structured:
        summary_for_memory = (
            f"{label}\nFacts: {len(structured['facts'])} | "
            f"Uncertainties: {len(structured['uncertainties'])}"
        )
        remember("media:" + hashlib.sha256(url.encode()).hexdigest()[:16], summary_for_memory)
        save_message("assistant", f"Media study — {label}\n{json.dumps(structured, indent=2)}")
        return {"structured": structured, "raw": raw, "stored": True}

    # Honest fallback: surface the parse failure rather than inventing structure.
    remember("media:" + hashlib.sha256(url.encode()).hexdigest()[:16], f"{label}\n{raw[:6000]}")
    save_message("assistant", f"Media study — {label}\n{raw}")
    return {"structured": None, "raw": raw, "parse_error": parse_error, "stored": True}
