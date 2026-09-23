"""Minimal Gemini REST provider; optional and free-tier compatible."""
import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY", "").strip())


def list_models() -> list[dict]:
    """Queries Google's own ListModels endpoint for this API key -- the
    reliable way to find a currently-valid model name, since Google
    renames/retires Gemini model IDs often enough that a hardcoded guess
    here can silently start 404ing months later."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Gemini is not configured")
    req = Request(f"https://generativelanguage.googleapis.com/v1beta/models?key={key}")
    with urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode())
    out = []
    for m in data.get("models", []):
        methods = m.get("supportedGenerationMethods", [])
        if "generateContent" in methods:
            out.append({"name": m.get("name", "").removeprefix("models/"), "display_name": m.get("displayName", "")})
    return out


def respond(messages, model=None) -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Gemini is not configured")
    model = model or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    system = ""
    contents = []
    for m in messages:
        role = m.get("role", "user")
        text = m.get("content", "")
        if role == "system":
            system += text + "\n"
        else:
            contents.append({"role": "model" if role == "assistant" else "user", "parts": [{"text": text}]})
    if system:
        contents.insert(0, {"role": "user", "parts": [{"text": "SYSTEM INSTRUCTIONS:\n" + system}]})
        contents.insert(1, {"role": "model", "parts": [{"text": "Understood."}]})
    payload = json.dumps({"contents": contents, "generationConfig": {"temperature": 0.55, "maxOutputTokens": 1400}}).encode()
    req = Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=45) as r:
            data = json.loads(r.read().decode())
    except HTTPError as exc:
        if exc.code == 404:
            raise RuntimeError(
                f"Gemini model '{model}' was not found for this API key (Google renames/retires model "
                f"IDs periodically). Call GET /api/system/gemini/models to see currently valid models "
                f"for your key, then set GEMINI_MODEL to one of them."
            ) from exc
        raise
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    answer = "".join(p.get("text", "") for p in parts).strip()
    if not answer:
        raise RuntimeError("Gemini returned no text")
    return answer
