"""Minimal Gemini REST provider; optional and free-tier compatible."""
import json
import os
from urllib.request import Request, urlopen


def configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY", "").strip())


def respond(messages, model=None) -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Gemini is not configured")
    model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
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
    with urlopen(req, timeout=45) as r:
        data = json.loads(r.read().decode())
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    answer = "".join(p.get("text", "") for p in parts).strip()
    if not answer:
        raise RuntimeError("Gemini returned no text")
    return answer
